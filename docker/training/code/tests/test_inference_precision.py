"""Tests for GPU inference precision selection."""

import pytest
import torch

from bda.config import _validate_optional_values
from inference import resolve_inference_precision


def test_resolve_inference_precision_when_cpu_auto_returns_fp32() -> None:
    device = torch.device("cpu")

    precision = resolve_inference_precision(device, "auto")

    assert precision == "fp32"


def test_resolve_inference_precision_when_ampere_auto_returns_bf16() -> None:
    device = torch.device("cuda:0")

    precision = resolve_inference_precision(
        device, "auto", compute_capability=(8, 0)
    )

    assert precision == "bf16"


def test_resolve_inference_precision_when_gpu_is_unsupported_rejects_bf16() -> None:
    device = torch.device("cuda:0")

    with pytest.raises(RuntimeError, match="BF16 inference is not supported"):
        resolve_inference_precision(
            device, "bf16", compute_capability=(7, 5)
        )


def test_validate_optional_values_when_precision_is_invalid_rejects_config() -> None:
    config = {"inference": {"precision": "fp8"}}

    with pytest.raises(ValueError, match="inference.precision"):
        _validate_optional_values(config)
