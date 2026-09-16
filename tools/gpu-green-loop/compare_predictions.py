"""Compare FP32 and BF16 HASTE inference class maps."""

import argparse
import json
from pathlib import Path

import numpy as np


def compare_predictions(
    baseline: np.ndarray, candidate: np.ndarray
) -> dict[str, float]:
    """Return shape and exact class-map agreement metrics."""
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


def parse_args() -> argparse.Namespace:
    """Parse comparison arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--minimum-agreement", type=float, default=0.999)
    return parser.parse_args()


def main() -> None:
    """Compare two saved prediction arrays."""
    args = parse_args()
    if not 0.0 <= args.minimum_agreement <= 1.0:
        raise ValueError("Minimum agreement must be between 0 and 1")
    result = compare_predictions(
        np.load(args.baseline), np.load(args.candidate)
    )
    print(json.dumps(result, indent=2))
    if result["agreement"] < args.minimum_agreement:
        raise SystemExit(
            f"Agreement {result['agreement']:.6f} is below "
            f"{args.minimum_agreement:.6f}"
        )


if __name__ == "__main__":
    main()
