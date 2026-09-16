"""Benchmark HASTE segmentation inference with synchronized NVML sampling."""

import argparse
import importlib.util
import itertools
import json
import math
import statistics
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import rasterio
import torch
from rasterio.transform import from_origin
from rasterio.windows import Window

from bda.trainers import CustomSemanticSegmentationTask

METRICS_PREFIX = "##GPU_METRICS##"
PredictBatch = Callable[
    [CustomSemanticSegmentationTask, torch.Tensor, torch.device], torch.Tensor
]


@dataclass(frozen=True)
class PowerSample:
    timestamp_s: float
    power_w: float
    utilization_pct: float
    memory_mib: float


def integrate_energy_joules(samples: list[PowerSample]) -> float:
    """Integrate sampled GPU power with the trapezoidal rule."""
    return sum(
        (right.timestamp_s - left.timestamp_s)
        * (left.power_w + right.power_w)
        / 2.0
        for left, right in itertools.pairwise(samples)
    )


def summarize_samples(samples: list[PowerSample]) -> dict[str, float]:
    """Summarize raw NVML samples."""
    if not samples:
        return {
            "gpu_energy_j": 0.0,
            "gpu_power_mean_w": 0.0,
            "gpu_power_peak_w": 0.0,
            "gpu_utilization_mean_pct": 0.0,
            "gpu_utilization_peak_pct": 0.0,
            "gpu_memory_peak_mib": 0.0,
        }
    return {
        "gpu_energy_j": integrate_energy_joules(samples),
        "gpu_power_mean_w": statistics.fmean(s.power_w for s in samples),
        "gpu_power_peak_w": max(s.power_w for s in samples),
        "gpu_utilization_mean_pct": statistics.fmean(
            s.utilization_pct for s in samples
        ),
        "gpu_utilization_peak_pct": max(s.utilization_pct for s in samples),
        "gpu_memory_peak_mib": max(s.memory_mib for s in samples),
    }


def parse_power_sample(line: str, timestamp_s: float) -> PowerSample:
    """Parse one line from an NVML-backed nvidia-smi query."""
    values = [float(value.strip()) for value in line.split(",")]
    if len(values) != 3:
        raise ValueError(f"Unexpected nvidia-smi output: {line!r}")
    return PowerSample(timestamp_s, *values)


def select_measurement_samples(
    samples: list[PowerSample], started_s: float, ended_s: float
) -> list[PowerSample]:
    """Clamp absolute telemetry samples to one measured interval."""
    if not samples or ended_s <= started_s:
        return []
    before = [sample for sample in samples if sample.timestamp_s <= started_s]
    during = [
        sample
        for sample in samples
        if started_s < sample.timestamp_s < ended_s
    ]
    after = [sample for sample in samples if sample.timestamp_s >= ended_s]
    first = before[-1] if before else (during[0] if during else samples[0])
    last = after[0] if after else (during[-1] if during else samples[-1])
    bounded = [
        PowerSample(0.0, first.power_w, first.utilization_pct, first.memory_mib),
        *[
            PowerSample(
                sample.timestamp_s - started_s,
                sample.power_w,
                sample.utilization_pct,
                sample.memory_mib,
            )
            for sample in during
        ],
        PowerSample(
            ended_s - started_s,
            last.power_w,
            last.utilization_pct,
            last.memory_mib,
        ),
    ]
    return bounded


class NvidiaSmiSampler:
    """Sample one GPU until stopped."""

    def __init__(self, device_index: int, interval_s: float) -> None:
        self.device_index = device_index
        self.interval_s = interval_s
        self.samples: list[PowerSample] = []
        self.error: Exception | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen[str] | None = None

    def start(self) -> None:
        interval_ms = max(1, round(self.interval_s * 1000))
        self._process = subprocess.Popen(
            [
                "nvidia-smi",
                f"--id={self.device_index}",
                "--query-gpu=power.draw,utilization.gpu,memory.used",
                "--format=csv,noheader,nounits",
                f"--loop-ms={interval_ms}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        def sample() -> None:
            assert self._process is not None
            assert self._process.stdout is not None
            try:
                for line in self._process.stdout:
                    self.samples.append(
                        parse_power_sample(line, time.perf_counter())
                    )
                    self._ready.set()
                    if self._stop.is_set():
                        return
            except (OSError, ValueError) as error:
                self.error = error
                self._ready.set()

        self._thread = threading.Thread(target=sample, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            self.stop()
            raise RuntimeError("GPU telemetry did not produce a sample")
        if self.error is not None:
            self.stop()
            raise RuntimeError("GPU telemetry sampling failed") from self.error

    def stop(self) -> list[PowerSample]:
        self._stop.set()
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
        if self._thread is not None:
            self._thread.join()
        if self._process is not None:
            self._process.wait()
        if self.error is not None:
            raise RuntimeError("GPU telemetry sampling failed") from self.error
        return self.samples


def autocast_context(precision: str):
    """Return the requested inference precision context."""
    return torch.amp.autocast(
        "cuda",
        dtype=torch.bfloat16,
        enabled=precision == "bf16",
    )


def load_candidate(candidate_path: Path) -> PredictBatch:
    """Load a candidate's predict_batch function."""
    spec = importlib.util.spec_from_file_location(
        "gepa_inference_candidate", candidate_path
    )
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load candidate module: {candidate_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    predict_batch = getattr(module, "predict_batch", None)
    if not callable(predict_batch):
        raise ValueError("Candidate must define callable predict_batch")
    return predict_batch


def build_task(checkpoint_path: Path) -> CustomSemanticSegmentationTask:
    """Build the production architecture and load fixed benchmark weights."""
    torch.manual_seed(20260915)
    task = CustomSemanticSegmentationTask(
        model="unet",
        backbone="resnext50_32x4d",
        weights=False,
        in_channels=3,
        num_classes=4,
        loss="ce",
        ignore_index=0,
        lr=0.0001,
        patience=10,
    )
    if checkpoint_path.exists():
        task.load_state_dict(
            torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        )
    else:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(task.state_dict(), checkpoint_path)
    return task


def ensure_raster_fixture(raster_path: Path, patch_size: int) -> None:
    """Create a deterministic tiled GeoTIFF fixture when absent."""
    if raster_path.exists():
        return
    side = max(2048, patch_size * 4)
    generator = np.random.default_rng(20260915)
    imagery = generator.integers(
        0, 256, size=(3, side, side), dtype=np.uint8
    )
    raster_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        width=side,
        height=side,
        count=3,
        dtype="uint8",
        crs="EPSG:32604",
        transform=from_origin(600000.0, 2300000.0, 0.5, 0.5),
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress="lzw",
    ) as raster:
        raster.write(imagery)


def create_batches(
    raster_path: Path, count: int, batch_size: int, patch_size: int
) -> list[torch.Tensor]:
    """Read deterministic raster windows into pinned normalized host batches."""
    batches = []
    with rasterio.open(raster_path) as raster:
        positions = [
            (x, y)
            for y in range(0, raster.height - patch_size + 1, patch_size)
            for x in range(0, raster.width - patch_size + 1, patch_size)
        ]
        for batch_index in range(count):
            images = torch.empty(
                batch_size,
                3,
                patch_size,
                patch_size,
                dtype=torch.float32,
                pin_memory=True,
            )
            for image_index in range(batch_size):
                position = positions[
                    (batch_index * batch_size + image_index) % len(positions)
                ]
                data = raster.read(
                    window=Window(*position, patch_size, patch_size)
                )
                images[image_index].copy_(torch.from_numpy(data))
            batches.append(images.div_(255.0))
    return batches


def write_prediction_cog(
    predictions: np.ndarray,
    source_path: Path,
    output_path: Path,
    patch_size: int,
) -> dict:
    """Assemble one raster pass and write a georeferenced prediction COG."""
    with rasterio.open(source_path) as source:
        expected_patches = math.ceil(source.width / patch_size) * math.ceil(
            source.height / patch_size
        )
        if len(predictions) < expected_patches:
            raise ValueError(
                f"Need {expected_patches} predictions, got {len(predictions)}"
            )
        class_map = np.full(
            (source.height, source.width), 255, dtype=np.uint8
        )
        prediction_index = 0
        for y in range(0, source.height, patch_size):
            for x in range(0, source.width, patch_size):
                height = min(patch_size, source.height - y)
                width = min(patch_size, source.width - x)
                class_map[y : y + height, x : x + width] = predictions[
                    prediction_index, :height, :width
                ]
                prediction_index += 1
        expected = {
            "width": source.width,
            "height": source.height,
            "crs": source.crs,
            "transform": source.transform,
            "bounds": source.bounds,
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        output_path,
        "w",
        driver="COG",
        width=expected["width"],
        height=expected["height"],
        count=1,
        dtype="uint8",
        crs=expected["crs"],
        transform=expected["transform"],
        nodata=255,
        compress="LZW",
        blocksize=256,
    ) as output:
        output.write(class_map, 1)

    with rasterio.open(output_path) as output:
        image_structure = output.tags(ns="IMAGE_STRUCTURE")
        tiled = all(
            block_height < output.height and block_width < output.width
            for block_height, block_width in output.block_shapes
        )
        validation = {
            "width": output.width,
            "height": output.height,
            "crs": str(output.crs),
            "transform": list(output.transform),
            "bounds": list(output.bounds),
            "nodata": output.nodata,
            "compression": output.compression.name,
            "tiled": tiled,
            "block_shapes": [list(shape) for shape in output.block_shapes],
            "layout": image_structure.get("LAYOUT"),
            "classes_min": int(output.read(1).min()),
            "classes_max": int(output.read(1).max()),
        }
        if (
            output.width != expected["width"]
            or output.height != expected["height"]
            or output.crs != expected["crs"]
            or output.transform != expected["transform"]
            or output.bounds != expected["bounds"]
            or output.nodata != 255
            or not tiled
            or image_structure.get("LAYOUT") != "COG"
            or validation["classes_max"] > 3
        ):
            raise ValueError(f"Prediction COG validation failed: {validation}")
    return validation


def run_batches(
    task: CustomSemanticSegmentationTask,
    batches: list[torch.Tensor],
    precision: str,
    predict_batch: PredictBatch | None = None,
    validate_output: bool = False,
) -> tuple[np.ndarray, float, float]:
    """Run synchronized inference and return class maps plus elapsed time."""
    outputs = []
    device = torch.device("cuda")
    torch.cuda.synchronize()
    started_s = time.perf_counter()
    with torch.inference_mode():
        for images in batches:
            if predict_batch is None:
                with autocast_context(precision):
                    logits = task(images.to(device, non_blocking=True))
            else:
                logits = predict_batch(task, images, device)
            if validate_output:
                expected_shape = (
                    images.shape[0],
                    4,
                    images.shape[2],
                    images.shape[3],
                )
                if (
                    not isinstance(logits, torch.Tensor)
                    or tuple(logits.shape) != expected_shape
                    or not torch.is_floating_point(logits)
                    or not torch.isfinite(logits).all().item()
                ):
                    raise ValueError(
                        "Candidate returned invalid logits; expected finite "
                        f"floating tensor with shape {expected_shape}"
                    )
            outputs.append(logits.argmax(dim=1).cpu())
    torch.cuda.synchronize()
    ended_s = time.perf_counter()
    return torch.cat(outputs).numpy().astype(np.uint8), started_s, ended_s


def parse_args() -> argparse.Namespace:
    """Parse benchmark arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--precision",
        choices=("fp32", "bf16", "candidate"),
        default="fp32",
    )
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--batches", type=int, default=40)
    parser.add_argument("--patch-size", type=int, default=256)
    parser.add_argument("--warmup-batches", type=int, default=5)
    parser.add_argument("--sample-interval-ms", type=float, default=50.0)
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    """Run one benchmark sample and write predictions plus metrics."""
    args = parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the GPU inference benchmark")
    if args.gpu < 0 or args.gpu >= torch.cuda.device_count():
        raise ValueError(f"GPU index {args.gpu} is not visible")
    if args.batch_size < 1 or args.batches < 1 or args.patch_size < 32:
        raise ValueError("Batch size/count must be positive; patch size must be >= 32")
    if args.sample_interval_ms <= 0 or not math.isfinite(
        args.sample_interval_ms
    ):
        raise ValueError("Sample interval must be a positive finite value")
    if (args.precision == "candidate") != (args.candidate is not None):
        raise ValueError(
            "--candidate must be provided exactly when precision is candidate"
        )

    torch.cuda.set_device(args.gpu)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.set_float32_matmul_precision("high")

    benchmark_started_s = time.perf_counter()
    raster_path = args.fixture_dir / "inference-fixture.tif"
    checkpoint_path = args.fixture_dir / "inference-fixture-state.pt"
    ensure_raster_fixture(raster_path, args.patch_size)
    model_setup_started_s = time.perf_counter()
    task = build_task(checkpoint_path).eval().to("cuda")
    model_setup_time_s = time.perf_counter() - model_setup_started_s
    batch_setup_started_s = time.perf_counter()
    warmup = create_batches(
        raster_path,
        args.warmup_batches,
        args.batch_size,
        args.patch_size,
    )
    measured = create_batches(
        raster_path, args.batches, args.batch_size, args.patch_size
    )
    batch_setup_time_s = time.perf_counter() - batch_setup_started_s
    predict_batch = (
        load_candidate(args.candidate)
        if args.candidate is not None
        else None
    )
    warmup_started_s = time.perf_counter()
    run_batches(
        task,
        warmup,
        args.precision,
        predict_batch=predict_batch,
        validate_output=predict_batch is not None,
    )
    warmup_time_s = time.perf_counter() - warmup_started_s

    torch.cuda.reset_peak_memory_stats()
    sampler = NvidiaSmiSampler(args.gpu, args.sample_interval_ms / 1000.0)
    sampler.start()
    process_started_s = time.process_time()
    predictions, started_s, ended_s = run_batches(
        task,
        measured,
        args.precision,
        predict_batch=predict_batch,
    )
    process_cpu_s = time.process_time() - process_started_s
    samples = select_measurement_samples(
        sampler.stop(), started_s, ended_s
    )
    elapsed_s = ended_s - started_s

    work_units = args.batch_size * args.batches
    summary = {
        "schema": "haste-gpu-green-loop/inference@1",
        "precision": args.precision,
        "gpu": {
            "index": args.gpu,
            "name": torch.cuda.get_device_name(args.gpu),
            "compute_capability": ".".join(
                str(value)
                for value in torch.cuda.get_device_capability(args.gpu)
            ),
        },
        "software": {
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
        },
        "workload": {
            "checkpoint": str(checkpoint_path),
            "raster": str(raster_path),
            "batch_size": args.batch_size,
            "batches": args.batches,
            "patch_size": args.patch_size,
            "patches": work_units,
        },
        "inference_wall_time_s": elapsed_s,
        "process_cpu_time_s": process_cpu_s,
        "model_setup_time_s": model_setup_time_s,
        "batch_setup_time_s": batch_setup_time_s,
        "warmup_time_s": warmup_time_s,
        "patches_per_second": work_units / elapsed_s,
        "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "cuda_peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        **summarize_samples(samples),
        "power_samples": [asdict(sample) for sample in samples],
    }
    energy_j = summary["gpu_energy_j"]
    summary["patches_per_joule"] = (
        work_units / energy_j if energy_j > 0 else None
    )

    args.output.mkdir(parents=True, exist_ok=True)
    np.save(args.output / f"predictions-{args.precision}.npy", predictions)
    output_started_s = time.perf_counter()
    summary["prediction_cog"] = write_prediction_cog(
        predictions,
        raster_path,
        args.output / f"predictions-{args.precision}.tif",
        args.patch_size,
    )
    summary["output_write_time_s"] = time.perf_counter() - output_started_s
    summary["benchmark_wall_time_s"] = (
        time.perf_counter() - benchmark_started_s
    )
    metrics_path = args.output / f"metrics-{args.precision}.json"
    metrics_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"{METRICS_PREFIX} {json.dumps(summary)}")


if __name__ == "__main__":
    main()
