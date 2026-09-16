"""Summarize repeated GPU green-loop measurements."""

import argparse
import json
import statistics
from pathlib import Path

SUMMARY_METRICS = (
    "inference_wall_time_s",
    "process_cpu_time_s",
    "model_setup_time_s",
    "batch_setup_time_s",
    "warmup_time_s",
    "output_write_time_s",
    "benchmark_wall_time_s",
    "patches_per_second",
    "gpu_energy_j",
    "patches_per_joule",
    "gpu_power_mean_w",
    "gpu_power_peak_w",
    "gpu_utilization_mean_pct",
    "gpu_utilization_peak_pct",
    "gpu_memory_peak_mib",
    "cuda_peak_allocated_bytes",
    "cuda_peak_reserved_bytes",
)


def summarize(records: list[dict]) -> dict:
    """Return medians and raw values for repeated measurements."""
    if not records:
        raise ValueError("At least one measurement is required")
    metrics = {}
    for name in SUMMARY_METRICS:
        values = [record[name] for record in records if record[name] is not None]
        if values:
            metrics[name] = {
                "median": statistics.median(values),
                "values": values,
            }
    return {
        "schema": "haste-gpu-green-loop/summary@1",
        "runs": len(records),
        "precision": records[0]["precision"],
        "gpu": records[0]["gpu"],
        "software": records[0]["software"],
        "workload": records[0]["workload"],
        "metrics": metrics,
    }


def parse_args() -> argparse.Namespace:
    """Parse summary arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("measurements", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    """Load measurements and write their median summary."""
    args = parse_args()
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in args.measurements
    ]
    result = summarize(records)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
