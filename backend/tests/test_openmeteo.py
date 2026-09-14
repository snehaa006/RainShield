"""Open-Meteo response parsing, exercised against a synthesised response.

The upstream API is not reachable from CI, so these tests drive the parser with
a payload shaped exactly like a real multi-coordinate Open-Meteo response.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from rainshield.config import LEAD_TIMES, REGION
from rainshield.ingest.mesh import mesh_query_pairs
from rainshield.ingest.openmeteo import OpenMeteoProvider

MESH = 5
N_HOURS = 72
#: Index of "now" in the hourly axis — past_days=1 puts it 24 hours in.
NOW_INDEX = 24


def _response(precip_per_location=None):
    """Build a response with one entry per mesh point."""
    lats, _ = mesh_query_pairs(MESH)
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(
        hours=NOW_INDEX
    )
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(N_HOURS)]

    out = []
    for i in range(len(lats)):
        precip = (
            precip_per_location[i]
            if precip_per_location is not None
            else [float(h % 5) for h in range(N_HOURS)]
        )
        out.append(
            {
                "latitude": lats[i],
                "hourly": {
                    "time": times,
                    "precipitation": precip,
                    "soil_moisture_0_to_7cm": [0.3] * N_HOURS,
                    "cloud_cover": [60.0] * N_HOURS,
                },
            }
        )
    return out


@pytest.fixture
def provider(monkeypatch):
    p = OpenMeteoProvider(mesh_size=MESH)
    monkeypatch.setattr(p, "_request", lambda: _response())
    return p


def test_fetch_produces_every_lead_time(provider):
    observation = provider.fetch()
    observation.validate()  # raises on any shape or lead-time gap

    assert observation.source == "openmeteo"
    assert not observation.degraded
    assert set(observation.rain_rate) == set(LEAD_TIMES)
    for lead in LEAD_TIMES:
        assert observation.rain_rate[lead].shape == REGION.shape
        assert observation.rain_3h[lead].shape == REGION.shape


def test_values_are_physical(provider):
    observation = provider.fetch()
    for lead in LEAD_TIMES:
        assert np.all(observation.rain_rate[lead] >= 0.0)
        assert np.all(observation.rain_3h[lead] >= 0.0)
    assert np.all((observation.soil_moisture >= 0.0) & (observation.soil_moisture <= 1.0))
    assert np.all((observation.cloud_cover >= 0.0) & (observation.cloud_cover <= 100.0))
    assert np.all(observation.antecedent_24h >= 0.0)


def test_nulls_are_treated_as_zero(monkeypatch):
    """Open-Meteo returns null for gaps; those must not become NaN."""
    payload = _response()
    for location in payload:
        location["hourly"]["precipitation"][NOW_INDEX] = None
    p = OpenMeteoProvider(mesh_size=MESH)
    monkeypatch.setattr(p, "_request", lambda: payload)

    observation = p.fetch()
    assert np.all(np.isfinite(observation.rain_rate[0]))


def test_north_south_gradient_is_preserved(monkeypatch):
    """A mesh that is wet in the north must yield a north-heavy grid.

    Guards the latitude orientation: Stage 0 splined over ascending latitudes
    into a north-up raster, which flipped those layers.
    """
    lats, _ = mesh_query_pairs(MESH)
    north = max(lats)
    precip = [
        [(20.0 if lat == north else 0.0)] * N_HOURS for lat in lats
    ]
    p = OpenMeteoProvider(mesh_size=MESH)
    monkeypatch.setattr(p, "_request", lambda: _response(precip))

    observation = p.fetch()
    grid = observation.rain_rate[0]
    assert grid[0].mean() > grid[-1].mean(), "row 0 must be the northern edge"


def test_rejects_short_response(monkeypatch):
    """A response with fewer points than the mesh must fail, not reshape."""
    truncated = _response()[:3]
    p = OpenMeteoProvider(mesh_size=MESH)
    monkeypatch.setattr(p, "_request", lambda: truncated)
    with pytest.raises(ValueError):
        p.fetch()
