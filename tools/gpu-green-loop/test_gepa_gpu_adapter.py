"""Tests for the isolated GEPA GPU adapter."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

GEPA_TOOLS = Path(__file__).parent / "gepa"
sys.path.insert(0, str(GEPA_TOOLS))

from gepa_gpu_adapter import (  # noqa: E402
    AdapterSettings,
    EVALUATION_SCHEMA,
    build_docker_create_command,
    build_docker_exec_command,
    candidate_id,
    pareto_frontier,
    rejection,
    validate_candidate_source,
)

VALID_CANDIDATE = """
import torch

def predict_batch(task, images, device):
    with torch.amp.autocast("cuda", dtype=torch.bfloat16):
        return task(images.to(device, non_blocking=True))
"""


def test_validate_candidate_source_when_contract_is_valid_accepts_source() -> None:
    tree = validate_candidate_source(VALID_CANDIDATE)

    assert tree.body


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("", "cannot be empty"),
        ("def nope(): pass", "exactly one synchronous predict_batch"),
        (
            "def predict_batch(task, images): return images",
            "must accept exactly",
        ),
        (
            "import os\ndef predict_batch(task, images, device): return images",
            "imports are restricted",
        ),
        (
            "def predict_batch(task, images, device): return open('/tmp/x')",
            "call is not allowed",
        ),
        (
            "def predict_batch(task, images, device): return task.__dict__",
            "dunder access",
        ),
    ],
)
def test_validate_candidate_source_when_policy_is_violated_rejects_source(
    source: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_candidate_source(source)


def test_candidate_id_when_source_is_same_is_stable() -> None:
    assert candidate_id(VALID_CANDIDATE) == candidate_id(VALID_CANDIDATE)
    assert len(candidate_id(VALID_CANDIDATE)) == 16


def test_rejection_exposes_gepa_multi_objective_scores() -> None:
    _, result = rejection(VALID_CANDIDATE, "test rejection")

    assert result["scores"] == result["objective_scores"]


def test_adapter_settings_when_repetitions_are_odd_rejects_value() -> None:
    with pytest.raises(
        ValidationError, match="repetitions must be even"
    ):
        AdapterSettings(repetitions=3)


def test_build_docker_create_command_applies_isolation_flags(
    tmp_path: Path,
) -> None:
    settings = AdapterSettings(
        docker_command=("sudo", "docker"),
        results_dir=tmp_path / "results",
        run_root=tmp_path / "gepa",
    )

    command = build_docker_create_command(settings, "test-container")

    assert command[:3] == ["sudo", "docker", "create"]
    assert ["--network", "none"] == command[
        command.index("--network") : command.index("--network") + 2
    ]
    assert "--read-only" in command
    assert ["--cap-drop", "ALL"] == command[
        command.index("--cap-drop") : command.index("--cap-drop") + 2
    ]
    assert "no-new-privileges" in command
    assert f"device={settings.gpu_index}" in command
    assert f"{settings.run_root / 'candidates'}:/candidates:ro" in command


def test_pareto_frontier_when_tradeoffs_exist_preserves_each_tradeoff() -> None:
    evaluations = [
        {
            "accepted": True,
            "candidate_id": "fast",
            "objective_scores": {
                "throughput": 1.2,
                "memory_efficiency": 1.0,
            },
        },
        {
            "accepted": True,
            "candidate_id": "small",
            "objective_scores": {
                "throughput": 1.0,
                "memory_efficiency": 1.2,
            },
        },
        {
            "accepted": True,
            "candidate_id": "dominated",
            "objective_scores": {
                "throughput": 0.9,
                "memory_efficiency": 0.9,
            },
        },
    ]

    frontier = pareto_frontier(evaluations)

    assert [item["candidate_id"] for item in frontier] == ["fast", "small"]


def test_pareto_frontier_when_evaluation_is_rejected_excludes_it() -> None:
    evaluations = [
        {
            "accepted": False,
            "candidate_id": "rejected",
            "objective_scores": {
                "throughput": 2.0,
                "memory_efficiency": 2.0,
            },
        }
    ]

    assert pareto_frontier(evaluations) == []


def test_build_docker_exec_command_uses_internal_timeout(
    tmp_path: Path,
) -> None:
    settings = AdapterSettings(
        docker_command=("sudo", "docker"),
        results_dir=tmp_path / "results",
        run_root=tmp_path / "gepa",
        timeout_seconds=120,
    )

    command = build_docker_exec_command(
        settings,
        "test-container",
        "candidate-id",
    )

    assert command[:3] == ["sudo", "docker", "exec"]
    assert command[3:7] == [
        "test-container",
        "timeout",
        "--signal=KILL",
        "120",
    ]
    assert "/candidates/candidate-id/candidate.py" in command
    assert "/candidates/seed-control/candidate.py" in command
    assert (
        f"/results/{EVALUATION_SCHEMA}/candidate-id-r"
        f"{settings.repetitions}"
    ) in command
    assert str(settings.repetitions) in command
