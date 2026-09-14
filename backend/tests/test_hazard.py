"""The hazard layer is what makes the dashboard respond to live weather."""

import numpy as np
import pytest

from rainshield.config import REGION
from rainshield.hazard import WhatIf, compute_hazard, confidence_for
from rainshield.risk import composite_risk, tier_array


@pytest.fixture
def susceptibility():
    """A north-to-south susceptibility ramp, independent of the checkpoint."""
    return np.linspace(0.05, 0.95, REGION.rows)[:, None] * np.ones((1, REGION.cols))


def _flat(value: float) -> np.ndarray:
    return np.full(REGION.shape, value, dtype=np.float32)


def test_no_rain_means_no_flooding(susceptibility):
    """However low-lying a cell is, it does not flood without rain."""
    hazard = compute_hazard(susceptibility, _flat(0.0), _flat(0.0), _flat(0.3), lead=0)
    assert hazard.flood_probability.max() == pytest.approx(0.0, abs=1e-6)
    assert hazard.water_depth.max() == pytest.approx(0.0, abs=1e-6)
    assert np.all(np.isnan(hazard.time_to_inundation))


def test_probability_rises_monotonically_with_rainfall(susceptibility):
    peaks = [
        compute_hazard(
            susceptibility, _flat(mm / 3), _flat(mm), _flat(0.3), lead=0
        ).flood_probability.max()
        for mm in (0, 10, 30, 60, 120, 200)
    ]
    assert peaks == sorted(peaks)
    assert peaks[-1] > 0.5, "extreme rainfall must produce a high probability"


def test_probability_never_exceeds_susceptibility(susceptibility):
    """Rainfall saturates the response; it cannot invent susceptibility."""
    hazard = compute_hazard(susceptibility, _flat(300.0), _flat(900.0), _flat(1.0), lead=0)
    assert np.all(hazard.flood_probability <= susceptibility + 1e-6)


def test_blocked_drainage_raises_hazard(susceptibility):
    baseline = compute_hazard(susceptibility, _flat(15.0), _flat(45.0), _flat(0.3), lead=0)
    blocked = compute_hazard(
        susceptibility,
        _flat(15.0),
        _flat(45.0),
        _flat(0.3),
        lead=0,
        what_if=WhatIf(drainage_capacity=0.4),
    )
    assert blocked.flood_probability.mean() > baseline.flood_probability.mean()
    assert blocked.water_depth.mean() > baseline.water_depth.mean()


def test_injected_rainfall_raises_hazard(susceptibility):
    baseline = compute_hazard(susceptibility, _flat(5.0), _flat(15.0), _flat(0.3), lead=0)
    injected = compute_hazard(
        susceptibility,
        _flat(5.0),
        _flat(15.0),
        _flat(0.3),
        lead=0,
        what_if=WhatIf(extra_rainfall=80.0),
    )
    assert injected.flood_probability.mean() > baseline.flood_probability.mean()


def test_time_to_inundation_only_where_probable(susceptibility):
    hazard = compute_hazard(susceptibility, _flat(20.0), _flat(60.0), _flat(0.4), lead=60)
    probable = hazard.flood_probability >= 0.35
    assert np.all(np.isfinite(hazard.time_to_inundation[probable]))
    assert np.all(np.isnan(hazard.time_to_inundation[~probable]))


def test_risk_stays_in_range_and_tiers_are_ordered(susceptibility):
    hazard = compute_hazard(susceptibility, _flat(40.0), _flat(120.0), _flat(0.5), lead=0)
    risk, components = composite_risk(hazard)

    assert np.all((risk >= 0.0) & (risk <= 1.0))
    for name, values in components.items():
        assert np.all((values >= 0.0) & (values <= 1.0)), name

    tiers = tier_array(np.array([0.1, 0.3, 0.6, 0.9]))
    assert list(tiers) == ["NORMAL", "WATCH", "WARNING", "CRITICAL"]


def test_confidence_degrades_with_lead_and_data_quality():
    assert confidence_for(0, degraded=False) == "HIGH"
    assert confidence_for(360, degraded=False) in {"MEDIUM", "LOW"}
    assert confidence_for(0, degraded=True) != "HIGH"
