"""Isolated GEPA adapter for HASTE GPU inference kernels."""

import argparse
import ast
import hashlib
import json
import math
import os
import shlex
import statistics
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RESULTS = REPO_ROOT / ".gpu-green-loop" / "results"
DEFAULT_RUN_ROOT = REPO_ROOT / ".gpu-green-loop" / "gepa"
SEED_CANDIDATE_PATH = Path(__file__).with_name("seed_candidate.py")
REQUIRED_AGREEMENT = 0.999
REPETITIONS = 4
MAX_CANDIDATE_BYTES = 24_000
REJECTED_SCORE = -1_000_000.0
EVALUATION_SCHEMA = "paired-process-v2"
MAX_THROUGHPUT_RATIO_DEVIATION = 0.10
ALLOWED_IMPORTS = {"torch"}
BLOCKED_CALLS = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "input",
    "open",
}
BLOCKED_ROOTS = {
    "asyncio",
    "builtins",
    "ctypes",
    "http",
    "importlib",
    "multiprocessing",
    "os",
    "pathlib",
    "shutil",
    "signal",
    "socket",
    "subprocess",
    "sys",
    "urllib",
}


class AdapterSettings(BaseModel):
    """Validated runtime settings for one GEPA GPU search."""

    model_config = ConfigDict(frozen=True)

    image: str = "haste-training:gpu-green-loop"
    gpu_index: int = Field(default=0, ge=0)
    repetitions: int = Field(default=REPETITIONS, ge=2, le=6)
    timeout_seconds: int = Field(default=900, ge=30, le=1800)
    candidate_budget: int = Field(default=12, ge=1, le=100)
    docker_command: tuple[str, ...] = ("docker",)
    results_dir: Path = DEFAULT_RESULTS
    run_root: Path = DEFAULT_RUN_ROOT

    @field_validator("docker_command")
    @classmethod
    def validate_docker_command(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        """Reject an empty Docker command."""
        if not value:
            raise ValueError("docker_command cannot be empty")
        return value

    @field_validator("repetitions")
    @classmethod
    def validate_repetitions(cls, value: int) -> int:
        """Require balanced control-first and candidate-first measurements."""
        if value % 2:
            raise ValueError("repetitions must be even for balanced pairing")
        return value


def validate_candidate_source(source: str) -> ast.Module:
    """Validate the inference-only source contract without executing it."""
    if not source.strip():
        raise ValueError("Candidate source cannot be empty")
    if len(source.encode("utf-8")) > MAX_CANDIDATE_BYTES:
        raise ValueError(
            f"Candidate exceeds {MAX_CANDIDATE_BYTES} byte source limit"
        )
    try:
        tree = ast.parse(source, filename="candidate.py")
    except SyntaxError as error:
        raise ValueError(f"Candidate syntax is invalid: {error}") from error

    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "predict_batch"
    ]
    if len(functions) != 1 or isinstance(functions[0], ast.AsyncFunctionDef):
        raise ValueError(
            "Candidate must define exactly one synchronous predict_batch"
        )
    if len(functions[0].args.args) != 3:
        raise ValueError(
            "predict_batch must accept exactly task, images, and device"
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = {alias.name.split(".", 1)[0] for alias in node.names}
            if not names <= ALLOWED_IMPORTS:
                raise ValueError(
                    f"Candidate imports are restricted to {ALLOWED_IMPORTS}"
                )
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root not in ALLOWED_IMPORTS:
                raise ValueError(
                    f"Candidate imports are restricted to {ALLOWED_IMPORTS}"
                )
        elif isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id in BLOCKED_CALLS
            ):
                raise ValueError(
                    f"Candidate call is not allowed: {node.func.id}"
                )
        elif isinstance(node, ast.Attribute):
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name) and root.id in BLOCKED_ROOTS:
                raise ValueError(
                    f"Candidate module access is not allowed: {root.id}"
                )
            if node.attr.startswith("__"):
                raise ValueError("Candidate dunder access is not allowed")
    return tree


def candidate_id(source: str) -> str:
    """Return a stable identifier for candidate source."""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def load_summary(path: Path) -> dict[str, Any]:
    """Load one benchmark summary with an explicit missing-file error."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Required baseline summary is missing: {path}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def median_metric(records: list[dict[str, Any]], name: str) -> float:
    """Return a finite median from candidate metric records."""
    values = [float(record[name]) for record in records]
    if not values or not all(np.isfinite(values)):
        raise ValueError(f"Metric {name} is missing or non-finite")
    return float(statistics.median(values))


def compare_predictions(
    baseline_path: Path, candidate_path: Path
) -> dict[str, float]:
    """Compare one candidate class map against its FP32 baseline."""
    baseline = np.load(baseline_path)
    candidate = np.load(candidate_path)
    if baseline.shape != candidate.shape:
        raise ValueError(
            f"Prediction shapes differ: {baseline.shape} != {candidate.shape}"
        )
    agreement = float(np.mean(baseline == candidate))
    return {
        "pixels": int(baseline.size),
        "agreement": agreement,
        "disagreement": 1.0 - agreement,
    }


def build_docker_create_command(
    settings: AdapterSettings, container_name: str
) -> list[str]:
    """Build the hardened persistent sandbox creation command."""
    return [
        *settings.docker_command,
        "create",
        "--name",
        container_name,
        "--gpus",
        f"device={settings.gpu_index}",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--shm-size",
        "1g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        "HOME=/tmp",
        "--tmpfs",
        "/tmp:rw,nosuid,noexec,size=1g",
        "--entrypoint",
        "sleep",
        "--volume",
        f"{TOOLS_DIR}:/benchmark:ro",
        "--volume",
        f"{settings.run_root / 'candidates'}:/candidates:ro",
        "--volume",
        f"{settings.results_dir.parent / 'fixtures'}:/fixtures:ro",
        "--volume",
        f"{settings.run_root / 'evaluations'}:/results",
        settings.image,
        "infinity",
    ]


def build_docker_exec_command(
    settings: AdapterSettings,
    container_name: str,
    candidate_key: str,
) -> list[str]:
    """Build one timed paired benchmark in the persistent sandbox."""
    return [
        *settings.docker_command,
        "exec",
        container_name,
        "timeout",
        "--signal=KILL",
        str(settings.timeout_seconds),
        "python",
        "/benchmark/gepa_pair_benchmark.py",
        "--control",
        "/candidates/seed-control/candidate.py",
        "--candidate",
        f"/candidates/{candidate_key}/candidate.py",
        "--gpu",
        "0",
        "--fixture-dir",
        "/fixtures",
        "--output",
        f"/results/{EVALUATION_SCHEMA}/{candidate_key}-r"
        f"{settings.repetitions}",
        "--repetitions",
        str(settings.repetitions),
    ]


class GpuSandbox:
    """Manage one hardened container for a serialized GEPA search."""

    def __init__(self, settings: AdapterSettings) -> None:
        self.settings = settings
        self.container_name = (
            f"haste-gepa-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.started = False

    def __enter__(self) -> "GpuSandbox":
        candidates = self.settings.run_root / "candidates"
        evaluations = self.settings.run_root / "evaluations"
        candidates.mkdir(parents=True, exist_ok=True)
        evaluations.mkdir(parents=True, exist_ok=True)
        command = build_docker_create_command(
            self.settings, self.container_name
        )
        created = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(900, self.settings.timeout_seconds),
        )
        if created.returncode != 0:
            raise RuntimeError(
                f"Failed to create GPU sandbox: {created.stderr[-2000:]}"
            )
        started = subprocess.run(
            [
                *self.settings.docker_command,
                "start",
                self.container_name,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=max(900, self.settings.timeout_seconds),
        )
        if started.returncode != 0:
            self.close()
            raise RuntimeError(
                f"Failed to start GPU sandbox: {started.stderr[-2000:]}"
            )
        self.started = True
        return self

    def run(
        self, candidate_key: str
    ) -> subprocess.CompletedProcess[str]:
        """Run one paired candidate evaluation with an outer timeout guard."""
        if not self.started:
            raise RuntimeError("GPU sandbox is not running")
        return subprocess.run(
            build_docker_exec_command(
                self.settings,
                self.container_name,
                candidate_key,
            ),
            check=False,
            capture_output=True,
            text=True,
            timeout=self.settings.timeout_seconds + 30,
        )

    def close(self) -> None:
        """Remove only this adapter's uniquely named container."""
        subprocess.run(
            [
                *self.settings.docker_command,
                "rm",
                "--force",
                self.container_name,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.started = False

    def __exit__(
        self,
        _exception_type: object,
        _exception: object,
        _traceback: object,
    ) -> None:
        self.close()


def rejection(
    candidate: str, reason: str, candidate_key: str | None = None
) -> tuple[float, dict[str, Any]]:
    """Return a GEPA-compatible rejecting result."""
    scores = {"throughput": 0.0, "memory_efficiency": 0.0}
    return REJECTED_SCORE, {
        "accepted": False,
        "candidate_id": candidate_key or candidate_id(candidate),
        "error": reason,
        "feedback": f"Candidate rejected: {reason}",
        "scores": scores,
        "objective_scores": scores,
    }


def evaluate_candidate(
    candidate: str,
    settings: AdapterSettings,
    sandbox: GpuSandbox | None = None,
) -> tuple[float, dict[str, Any]]:
    """Evaluate one candidate in isolated GPU containers."""
    key = candidate_id(candidate)
    try:
        validate_candidate_source(candidate)
    except ValueError as error:
        return rejection(candidate, str(error), key)

    fp32_summary = load_summary(settings.results_dir / "fp32-summary.json")
    candidate_root = settings.run_root / "candidates" / key
    candidate_root.mkdir(parents=True, exist_ok=True)
    candidate_path = candidate_root / "candidate.py"
    candidate_path.write_text(candidate, encoding="utf-8")
    seed_source = SEED_CANDIDATE_PATH.read_text(encoding="utf-8")
    validate_candidate_source(seed_source)
    seed_root = settings.run_root / "candidates" / "seed-control"
    seed_root.mkdir(parents=True, exist_ok=True)
    (seed_root / "candidate.py").write_text(seed_source, encoding="utf-8")

    if sandbox is None:
        with GpuSandbox(settings) as temporary_sandbox:
            return evaluate_candidate(
                candidate, settings, sandbox=temporary_sandbox
            )

    records: list[dict[str, Any]] = []
    control_records: list[dict[str, Any]] = []
    comparisons: list[dict[str, float]] = []
    evaluation_root = (
        settings.run_root
        / "evaluations"
        / EVALUATION_SCHEMA
        / f"{key}-r{settings.repetitions}"
    )
    manifest_path = evaluation_root / "manifest.json"
    if not manifest_path.is_file():
        try:
            completed = sandbox.run(key)
        except subprocess.TimeoutExpired:
            return rejection(
                candidate,
                f"GPU evaluation timed out after "
                f"{settings.timeout_seconds} seconds",
                key,
            )
        except RuntimeError as error:
            return rejection(candidate, str(error), key)
        evaluation_root.mkdir(parents=True, exist_ok=True)
        (evaluation_root / "stdout.log").write_text(
            completed.stdout, encoding="utf-8"
        )
        (evaluation_root / "stderr.log").write_text(
            completed.stderr, encoding="utf-8"
        )
        if completed.returncode != 0:
            return rejection(
                candidate,
                "GPU evaluation failed with exit code "
                f"{completed.returncode}. "
                f"stderr: {completed.stderr[-2000:]}",
                key,
            )

    for repetition in range(1, settings.repetitions + 1):
        pair_root = evaluation_root / f"pair-{repetition}"
        control_dir = pair_root / "control"
        candidate_dir = pair_root / "candidate"
        control_record = json.loads(
            (control_dir / "metrics.json").read_text(encoding="utf-8")
        )
        record = json.loads(
            (candidate_dir / "metrics.json").read_text(encoding="utf-8")
        )
        predictions_path = candidate_dir / "predictions.npy"
        comparison = compare_predictions(
            settings.results_dir
            / f"fp32-run-{repetition}"
            / "predictions-fp32.npy",
            predictions_path,
        )
        if comparison["agreement"] < REQUIRED_AGREEMENT:
            return rejection(
                candidate,
                f"prediction agreement {comparison['agreement']:.6f} "
                f"is below {REQUIRED_AGREEMENT:.6f}",
                key,
            )
        if repetition == 1:
            cog = record.get("prediction_cog", {})
            if not (
                cog.get("layout") == "COG"
                and cog.get("crs") == "EPSG:32604"
                and cog.get("nodata") == 255.0
                and cog.get("tiled") is True
                and 0 <= cog.get("classes_min", -1)
                and cog.get("classes_max", 256) <= 3
            ):
                return rejection(candidate, f"COG gate failed: {cog}", key)
        control_records.append(control_record)
        records.append(record)
        comparisons.append(comparison)

    fp32_metrics = fp32_summary["metrics"]
    patches_per_joule = median_metric(records, "patches_per_joule")
    patches_per_second = median_metric(records, "patches_per_second")
    reserved_bytes = median_metric(records, "cuda_peak_reserved_bytes")
    control_patches_per_joule = median_metric(
        control_records, "patches_per_joule"
    )
    control_patches_per_second = median_metric(
        control_records, "patches_per_second"
    )
    control_reserved_bytes = median_metric(
        control_records, "cuda_peak_reserved_bytes"
    )
    energy_efficiency = float(
        statistics.median(
            float(candidate_run["patches_per_joule"])
            / float(control_run["patches_per_joule"])
            for candidate_run, control_run in zip(
                records, control_records, strict=True
            )
        )
    )
    throughput = float(
        statistics.median(
            float(candidate_run["patches_per_second"])
            / float(control_run["patches_per_second"])
            for candidate_run, control_run in zip(
                records, control_records, strict=True
            )
        )
    )
    memory_efficiency = float(
        statistics.median(
            float(control_run["cuda_peak_reserved_bytes"])
            / float(candidate_run["cuda_peak_reserved_bytes"])
            for candidate_run, control_run in zip(
                records, control_records, strict=True
            )
        )
    )
    throughput_ratios = [
        float(candidate_run["patches_per_second"])
        / float(control_run["patches_per_second"])
        for candidate_run, control_run in zip(
            records, control_records, strict=True
        )
    ]
    max_throughput_ratio_deviation = max(
        abs(ratio / throughput - 1.0) for ratio in throughput_ratios
    )
    if (
        max_throughput_ratio_deviation
        > MAX_THROUGHPUT_RATIO_DEVIATION
    ):
        return rejection(
            candidate,
            "paired throughput ratios are unstable: maximum deviation "
            f"{max_throughput_ratio_deviation:.4f} exceeds "
            f"{MAX_THROUGHPUT_RATIO_DEVIATION:.4f}",
            key,
        )
    objective_scores = {
        "throughput": throughput,
        "memory_efficiency": memory_efficiency,
    }
    score = math.sqrt(throughput * memory_efficiency)
    result = {
        "accepted": True,
        "candidate_id": key,
        "score": score,
        "agreement": min(item["agreement"] for item in comparisons),
        "medians": {
            "inference_wall_time_s": median_metric(
                records, "inference_wall_time_s"
            ),
            "gpu_energy_j": median_metric(records, "gpu_energy_j"),
            "patches_per_second": patches_per_second,
            "patches_per_joule": patches_per_joule,
            "cuda_peak_reserved_bytes": reserved_bytes,
        },
        "control_medians": {
            "inference_wall_time_s": median_metric(
                control_records, "inference_wall_time_s"
            ),
            "gpu_energy_j": median_metric(
                control_records, "gpu_energy_j"
            ),
            "patches_per_second": control_patches_per_second,
            "patches_per_joule": control_patches_per_joule,
            "cuda_peak_reserved_bytes": control_reserved_bytes,
        },
        "objective_scores": objective_scores,
        "scores": objective_scores,
        "diagnostics": {
            "energy_efficiency": energy_efficiency,
            "throughput_ratios": throughput_ratios,
            "max_throughput_ratio_deviation": (
                max_throughput_ratio_deviation
            ),
        },
        "fp32_normalized": {
            "energy_efficiency": (
                patches_per_joule
                / float(fp32_metrics["patches_per_joule"]["median"])
            ),
            "throughput": (
                patches_per_second
                / float(fp32_metrics["patches_per_second"]["median"])
            ),
            "memory_efficiency": (
                float(
                    fp32_metrics["cuda_peak_reserved_bytes"]["median"]
                )
                / reserved_bytes
            ),
        },
        "feedback": (
            f"Accepted {key}. Pareto objectives: throughput "
            f"{throughput:.4f}, memory efficiency "
            f"{memory_efficiency:.4f}. Diagnostic energy efficiency "
            f"{energy_efficiency:.4f}; maximum paired throughput-ratio "
            f"deviation {max_throughput_ratio_deviation:.4f}. Minimum "
            "class-map agreement "
            f"{min(item['agreement'] for item in comparisons):.6f}."
        ),
        "control_runs": control_records,
        "runs": records,
        "comparisons": comparisons,
    }
    (candidate_root / "evaluation.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return score, result


def pareto_frontier(
    evaluations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return accepted evaluations not dominated on throughput and memory."""
    accepted = [
        evaluation
        for evaluation in evaluations
        if evaluation.get("accepted") is True
    ]
    frontier = []
    for candidate in accepted:
        candidate_scores = candidate["objective_scores"]
        dominated = any(
            other is not candidate
            and all(
                float(other["objective_scores"][objective])
                >= float(candidate_scores[objective])
                for objective in ("throughput", "memory_efficiency")
            )
            and any(
                float(other["objective_scores"][objective])
                > float(candidate_scores[objective])
                for objective in ("throughput", "memory_efficiency")
            )
            for other in accepted
        )
        if not dominated:
            frontier.append(candidate)
    return frontier


def run_gepa_search(
    seed_candidate: str,
    settings: AdapterSettings,
    reflection_model: str,
    sandbox: GpuSandbox,
) -> dict[str, Any]:
    """Run GEPA and persist the best inference candidate."""
    from gepa.optimize_anything import (
        EngineConfig,
        GEPAConfig,
        ReflectionConfig,
        optimize_anything,
    )

    search_dir = settings.run_root / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    calibration_score, calibration = evaluate_candidate(
        seed_candidate, settings, sandbox
    )
    calibration_objectives = calibration["objective_scores"]
    unstable = {
        name: value
        for name, value in calibration_objectives.items()
        if not 0.97 <= float(value) <= 1.03
    }
    if calibration_score == REJECTED_SCORE or unstable:
        raise RuntimeError(
            "Paired seed calibration is not stable enough for autonomous "
            f"search: {unstable or calibration.get('error')}"
        )

    def evaluator(
        candidate: str, _optimization_state: Any
    ) -> tuple[float, dict[str, Any]]:
        return evaluate_candidate(candidate, settings, sandbox)

    result = optimize_anything(
        seed_candidate=seed_candidate,
        evaluator=evaluator,
        config=GEPAConfig(
            engine=EngineConfig(
                run_dir=str(search_dir),
                max_candidate_proposals=settings.candidate_budget,
                parallel=False,
                cache_evaluation=True,
                track_best_outputs=True,
            ),
            reflection=ReflectionConfig(
                reflection_lm=reflection_model,
            ),
        ),
        objective=(
            "Improve HASTE A100 segmentation inference. Find the Pareto "
            "frontier for throughput and CUDA reserved-memory efficiency. "
            "Preserve at least 99.9% FP32 class-map agreement and all COG "
            "metadata. Return only the complete Python candidate module."
        ),
        background=(
            "The candidate defines predict_batch(task, images, device) and "
            "returns finite logits. The evaluator owns fixtures, timing, NVML "
            "energy diagnostics, correctness, and output. Energy is not a "
            "search objective while the GPU is shared. Only torch imports "
            "are allowed. "
            "Networking, files, subprocesses, dynamic execution, and dunder "
            "access are rejected."
        ),
    )
    candidate_key = result._str_candidate_key
    if candidate_key is None:
        raise RuntimeError("GEPA did not preserve string-candidate metadata")
    evaluations = []
    for index, candidate in enumerate(result.candidates):
        source = candidate[candidate_key]
        score, evaluation = evaluate_candidate(source, settings, sandbox)
        evaluation = {
            **evaluation,
            "gepa_candidate_index": index,
            "guide_score": score,
        }
        evaluations.append(evaluation)
    frontier = pareto_frontier(evaluations)
    frontier_dir = search_dir / "frontier"
    frontier_dir.mkdir(parents=True, exist_ok=True)
    for evaluation in frontier:
        index = int(evaluation["gepa_candidate_index"])
        source = result.candidates[index][candidate_key]
        path = frontier_dir / (
            f"candidate-{index}-{evaluation['candidate_id']}.py"
        )
        path.write_text(source, encoding="utf-8")
        evaluation["source_path"] = str(path)
    report = {
        "schema": "haste-gpu-green-loop/gepa-search@2",
        "reflection_model": reflection_model,
        "candidate_budget": settings.candidate_budget,
        "selection_policy": "pareto-frontier-no-automatic-winner",
        "guide_score": "geometric-mean-throughput-memory",
        "frontier": frontier,
        "evaluations": evaluations,
    }
    (search_dir / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def parse_args() -> argparse.Namespace:
    """Parse adapter CLI arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=("seed", "search"), help="Evaluation mode"
    )
    parser.add_argument(
        "--seed",
        type=Path,
        default=Path(__file__).with_name("seed_candidate.py"),
    )
    parser.add_argument("--image", default="haste-training:gpu-green-loop")
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--repetitions", type=int, default=REPETITIONS)
    parser.add_argument("--candidate-budget", type=int, default=12)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--docker-command",
        default=os.environ.get("HASTE_DOCKER_COMMAND", "docker"),
    )
    parser.add_argument(
        "--reflection-model",
        default=os.environ.get("GEPA_REFLECTION_MODEL"),
    )
    return parser.parse_args()


def main() -> None:
    """Evaluate the seed or launch the configured GEPA search."""
    args = parse_args()
    settings = AdapterSettings(
        image=args.image,
        gpu_index=args.gpu,
        repetitions=args.repetitions,
        candidate_budget=args.candidate_budget,
        timeout_seconds=args.timeout_seconds,
        docker_command=tuple(shlex.split(args.docker_command)),
    )
    seed_candidate = args.seed.read_text(encoding="utf-8")
    with GpuSandbox(settings) as sandbox:
        if args.mode == "seed":
            score, result = evaluate_candidate(
                seed_candidate, settings, sandbox
            )
            print(json.dumps({"score": score, **result}, indent=2))
            if not result["accepted"]:
                raise SystemExit(1)
            return
        if not args.reflection_model:
            raise ValueError(
                "Set GEPA_REFLECTION_MODEL or pass --reflection-model"
            )
        report = run_gepa_search(
            seed_candidate, settings, args.reflection_model, sandbox
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    sys.exit(main())
