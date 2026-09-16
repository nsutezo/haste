"""Unit tests for GPU green-loop calculation and correctness helpers."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from compare_predictions import compare_predictions
from gpu_inference_benchmark import (
    PowerSample,
    integrate_energy_joules,
    select_measurement_samples,
    write_prediction_cog,
)
from rasterio.transform import from_origin
from summarize_runs import summarize


def test_integrate_energy_when_power_is_constant_returns_joules() -> None:
    samples = [
        PowerSample(0.0, 100.0, 20.0, 1000.0),
        PowerSample(0.5, 100.0, 30.0, 1100.0),
        PowerSample(1.0, 100.0, 40.0, 1200.0),
    ]

    energy_j = integrate_energy_joules(samples)

    assert energy_j == 100.0


def test_integrate_energy_when_power_ramps_uses_trapezoidal_rule() -> None:
    samples = [
        PowerSample(0.0, 100.0, 20.0, 1000.0),
        PowerSample(2.0, 200.0, 40.0, 1200.0),
    ]

    energy_j = integrate_energy_joules(samples)

    assert energy_j == 300.0


def test_select_measurement_samples_when_samples_span_window_clamps_bounds() -> None:
    samples = [
        PowerSample(9.9, 90.0, 10.0, 1000.0),
        PowerSample(10.1, 110.0, 20.0, 1100.0),
        PowerSample(10.4, 140.0, 30.0, 1200.0),
        PowerSample(10.6, 160.0, 40.0, 1300.0),
    ]

    selected = select_measurement_samples(samples, 10.0, 10.5)

    assert [sample.timestamp_s for sample in selected] == pytest.approx(
        [0.0, 0.1, 0.4, 0.5]
    )
    assert [sample.power_w for sample in selected] == [
        90.0,
        110.0,
        140.0,
        160.0,
    ]


def test_select_measurement_samples_when_window_is_invalid_returns_empty() -> None:
    samples = [PowerSample(1.0, 100.0, 20.0, 1000.0)]

    selected = select_measurement_samples(samples, 2.0, 2.0)

    assert selected == []


def test_compare_predictions_when_maps_match_returns_full_agreement() -> None:
    predictions = np.array([[1, 2], [3, 0]], dtype=np.uint8)

    result = compare_predictions(predictions, predictions.copy())

    assert result["agreement"] == 1.0
    assert result["pixels"] == 4


def test_compare_predictions_when_shapes_differ_rejects_input() -> None:
    baseline = np.zeros((2, 2), dtype=np.uint8)
    candidate = np.zeros((4,), dtype=np.uint8)

    with pytest.raises(ValueError, match="shapes differ"):
        compare_predictions(baseline, candidate)


def test_write_prediction_cog_when_predictions_cover_source_preserves_geospatial_contract(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.tif"
    output_path = tmp_path / "predictions.tif"
    transform = from_origin(600000.0, 2300000.0, 0.5, 0.5)
    with rasterio.open(
        source_path,
        "w",
        driver="GTiff",
        width=512,
        height=512,
        count=3,
        dtype="uint8",
        crs="EPSG:32604",
        transform=transform,
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as source:
        source.write(np.zeros((3, 512, 512), dtype=np.uint8))
    predictions = np.stack(
        [np.full((256, 256), value, dtype=np.uint8) for value in range(4)]
    )

    result = write_prediction_cog(
        predictions, source_path, output_path, patch_size=256
    )

    assert result["crs"] == "EPSG:32604"
    assert result["transform"] == list(transform)
    assert result["bounds"] == [600000.0, 2299744.0, 600256.0, 2300000.0]
    assert result["nodata"] == 255.0
    assert result["tiled"] is True
    assert result["layout"] == "COG"
    assert result["classes_min"] == 0
    assert result["classes_max"] == 3


def test_write_prediction_cog_when_predictions_are_missing_rejects_input(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.tif"
    with rasterio.open(
        source_path,
        "w",
        driver="GTiff",
        width=512,
        height=512,
        count=3,
        dtype="uint8",
        crs="EPSG:32604",
        transform=from_origin(0.0, 512.0, 1.0, 1.0),
    ) as source:
        source.write(np.zeros((3, 512, 512), dtype=np.uint8))
    predictions = np.zeros((3, 256, 256), dtype=np.uint8)

    with pytest.raises(ValueError, match="Need 4 predictions"):
        write_prediction_cog(
            predictions,
            source_path,
            tmp_path / "predictions.tif",
            patch_size=256,
        )


def test_summarize_when_runs_exist_returns_metric_medians() -> None:
    records = [
        {
            "precision": "fp32",
            "gpu": {"name": "test-gpu"},
            "software": {"torch": "test"},
            "workload": {"patches": 8},
            "inference_wall_time_s": value,
            "process_cpu_time_s": value,
            "model_setup_time_s": value,
            "batch_setup_time_s": value,
            "warmup_time_s": value,
            "output_write_time_s": value,
            "benchmark_wall_time_s": value,
            "patches_per_second": value,
            "gpu_energy_j": value,
            "patches_per_joule": value,
            "gpu_power_mean_w": value,
            "gpu_power_peak_w": value,
            "gpu_utilization_mean_pct": value,
            "gpu_utilization_peak_pct": value,
            "gpu_memory_peak_mib": value,
            "cuda_peak_allocated_bytes": value,
            "cuda_peak_reserved_bytes": value,
        }
        for value in (1.0, 3.0, 2.0)
    ]

    result = summarize(records)

    assert result["runs"] == 3
    assert result["metrics"]["gpu_energy_j"]["median"] == 2.0
    assert result["metrics"]["gpu_energy_j"]["values"] == [1.0, 3.0, 2.0]


def test_summarize_when_runs_are_empty_rejects_input() -> None:
    with pytest.raises(ValueError, match="At least one measurement"):
        summarize([])
