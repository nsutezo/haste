"""Measure a GEPA candidate and seed control in one GPU process."""

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import torch

from gpu_inference_benchmark import (
    NvidiaSmiSampler,
    PredictBatch,
    build_task,
    create_batches,
    ensure_raster_fixture,
    load_candidate,
    run_batches,
    select_measurement_samples,
    summarize_samples,
    write_prediction_cog,
)


def parse_args() -> argparse.Namespace:
    """Parse paired benchmark arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--batches", type=int, default=40)
    parser.add_argument("--patch-size", type=int, default=256)
    parser.add_argument("--warmup-batches", type=int, default=5)
    parser.add_argument("--sample-interval-ms", type=float, default=50.0)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def measure(
    task: torch.nn.Module,
    batches: list[torch.Tensor],
    predict_batch: PredictBatch,
    args: argparse.Namespace,
    output_dir: Path,
    *,
    persist_predictions: bool,
    validate_cog: bool,
) -> dict[str, Any]:
    """Measure one already-loaded inference kernel."""
    torch.cuda.reset_peak_memory_stats()
    sampler = NvidiaSmiSampler(args.gpu, args.sample_interval_ms / 1000.0)
    sampler.start()
    process_started_s = time.process_time()
    predictions, started_s, ended_s = run_batches(
        task,
        batches,
        "candidate",
        predict_batch=predict_batch,
    )
    process_cpu_s = time.process_time() - process_started_s
    samples = select_measurement_samples(
        sampler.stop(), started_s, ended_s
    )
    elapsed_s = ended_s - started_s
    patches = args.batch_size * args.batches
    metrics = {
        "schema": "haste-gpu-green-loop/gepa-pair@1",
        "inference_wall_time_s": elapsed_s,
        "process_cpu_time_s": process_cpu_s,
        "patches_per_second": patches / elapsed_s,
        "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "cuda_peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        **summarize_samples(samples),
        "power_samples": [asdict(sample) for sample in samples],
    }
    energy_j = metrics["gpu_energy_j"]
    metrics["patches_per_joule"] = (
        patches / energy_j if energy_j > 0 else None
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    if persist_predictions:
        np.save(output_dir / "predictions.npy", predictions)
    if validate_cog:
        metrics["prediction_cog"] = write_prediction_cog(
            predictions,
            args.fixture_dir / "inference-fixture.tif",
            output_dir / "predictions.tif",
            args.patch_size,
        )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    return metrics


def main() -> None:
    """Run alternating control/candidate measurements."""
    args = parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the paired GPU benchmark")
    if args.repetitions < 1:
        raise ValueError("Repetitions must be positive")

    torch.cuda.set_device(args.gpu)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.set_float32_matmul_precision("high")

    raster_path = args.fixture_dir / "inference-fixture.tif"
    checkpoint_path = args.fixture_dir / "inference-fixture-state.pt"
    ensure_raster_fixture(raster_path, args.patch_size)
    task = build_task(checkpoint_path).eval().to("cuda")
    warmup = create_batches(
        raster_path,
        args.warmup_batches,
        args.batch_size,
        args.patch_size,
    )
    measured = create_batches(
        raster_path,
        args.batches,
        args.batch_size,
        args.patch_size,
    )
    kernels = {
        "control": load_candidate(args.control),
        "candidate": load_candidate(args.candidate),
    }
    for kernel in kernels.values():
        run_batches(
            task,
            warmup,
            "candidate",
            predict_batch=kernel,
            validate_output=True,
        )

    manifest = []
    for repetition in range(1, args.repetitions + 1):
        order = (
            ("control", "candidate")
            if repetition % 2
            else ("candidate", "control")
        )
        pair = {"repetition": repetition, "order": list(order)}
        for role in order:
            pair[role] = measure(
                task,
                measured,
                kernels[role],
                args,
                args.output / f"pair-{repetition}" / role,
                persist_predictions=role == "candidate",
                validate_cog=role == "candidate" and repetition == 1,
            )
        manifest.append(pair)
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
