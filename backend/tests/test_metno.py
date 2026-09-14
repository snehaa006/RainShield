"""MET Norway parsing and the provider fallback chain.

api.met.no is not reachable from CI, so the transport is stubbed and these
tests pin the response shape and the chain's behaviour.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from rainshield.config import LEAD_TIMES, REGION
from rainshield.ingest.metno import MetNoProvider

MESH = 3


def _payload(n_hours: int = 60, rain: float = 2.0, tail_6h: int = 8) -> dict:
    """A Locationforecast response: hourly entries, then 6-hourly ones."""
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    series = []
    for h in range(n_hours):
        series.append(
            {
                "time": (start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "data": {
                    "instant": {"details": {"cloud_area_fraction": 80.0}},
                    "next_1_hours": {"details": {"precipitation_amount": rain}},
                },
            }
        )
    # Beyond ~3 days met.no only gives 6-hourly blocks; these must be ignored.
    for h in range(tail_6h):
        series.append(
            {
                "time": (start + timedelta(hours=n_hours + h * 6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "data": {
                    "instant": {"details": {"cloud_area_fraction": 50.0}},
                    "next_6_hours": {"details": {"precipitation_amount": 9.0}},
                },
            }
        )
    return {"properties": {"timeseries": series}}


def _patch(monkeypatch, handler):
    import rainshield.ingest.metno as m

    class _Resp:
        def __init__(self, status, payload=None, text=""):
            self.status_code, self.ok, self._p, self.text = status, 200 <= status < 300, payload, text

        def json(self):
            return self._p

    monkeypatch.setattr(m.requests, "get", lambda url, **kw: handler(kw, _Resp))


def test_parses_hourly_entries_and_ignores_six_hourly():
    times, precip, cloud = MetNoProvider._parse(_payload(n_hours=40))
    assert len(times) == 40, "6-hourly tail entries must be dropped"
    assert len(precip) == 40 and len(cloud) == 40
    assert all(p == 2.0 for p in precip)


def test_fetch_builds_a_full_observation(monkeypatch):
    _patch(monkeypatch, lambda kw, R: R(200, _payload()))
    observation = MetNoProvider(mesh_size=MESH).fetch()
    observation.validate()

    assert observation.source == "metno"
    assert not observation.degraded
    assert set(observation.rain_rate) == set(LEAD_TIMES)
    for lead in LEAD_TIMES:
        assert observation.rain_rate[lead].shape == REGION.shape
        assert np.all(observation.rain_rate[lead] >= 0.0)
    # Forecast-only feed: soil moisture is substituted, so it must still be sane.
    assert np.all((observation.soil_moisture >= 0.0) & (observation.soil_moisture <= 1.0))
    assert any("forecast-only" in n for n in observation.notes)


def test_one_request_per_mesh_point(monkeypatch):
    calls = []

    def handler(kw, R):
        calls.append(kw["params"])
        return R(200, _payload())

    _patch(monkeypatch, handler)
    MetNoProvider(mesh_size=MESH).fetch()
    assert len(calls) == MESH * MESH


def test_sends_identifying_user_agent(monkeypatch):
    """MET Norway's terms require a descriptive User-Agent."""
    seen = {}

    def handler(kw, R):
        seen.update(kw["headers"])
        return R(200, _payload())

    _patch(monkeypatch, handler)
    MetNoProvider(mesh_size=MESH).fetch()
    assert "RainShield" in seen["User-Agent"]


def test_http_error_is_raised_with_context(monkeypatch):
    _patch(monkeypatch, lambda kw, R: R(403, None, "Forbidden: missing User-Agent"))
    with pytest.raises(RuntimeError, match="403"):
        MetNoProvider(mesh_size=MESH).fetch()


# -- fallback chain ---------------------------------------------------------


def test_chain_falls_through_to_the_second_source(monkeypatch):
    """A rate-limited Open-Meteo must reach met.no, not drop to synthetic."""
    import rainshield.ingest as ingest
    from rainshield.ingest.openmeteo import OpenMeteoError

    ingest.clear_cache()

    class _Dead:
        name = "openmeteo"

        def fetch(self):
            raise OpenMeteoError("HTTP 429: Daily API request limit exceeded", status=429)

    _patch(monkeypatch, lambda kw, R: R(200, _payload()))
    monkeypatch.setattr(ingest, "build_providers", lambda: [_Dead(), MetNoProvider(mesh_size=MESH)])

    observation = ingest.get_observation(force_refresh=True)
    assert observation.source == "metno"
    assert not observation.degraded, "a working second source is not a degraded feed"
    assert any("1 source(s) failed" in n for n in observation.notes)
    ingest.clear_cache()


def test_chain_falls_back_to_synthetic_when_all_sources_fail(monkeypatch):
    import rainshield.ingest as ingest

    ingest.clear_cache()

    class _Dead:
        def __init__(self, name):
            self.name = name

        def fetch(self):
            raise RuntimeError(f"{self.name} is down")

    monkeypatch.setattr(ingest, "build_providers", lambda: [_Dead("openmeteo"), _Dead("metno")])

    observation = ingest.get_observation(force_refresh=True)
    assert observation.source == "synthetic"
    assert observation.degraded
    assert any("every live source failed" in n for n in observation.notes)
    ingest.clear_cache()


def test_named_provider_is_a_preference_not_a_pin():
    """A named source must still fall back, or a rate limit means invented data."""
    from rainshield.ingest import build_providers

    assert [p.name for p in build_providers("openmeteo")] == ["openmeteo", "metno"]
    assert [p.name for p in build_providers("metno")] == ["metno", "openmeteo"]
    assert [p.name for p in build_providers("auto")] == ["openmeteo", "metno"]


def test_synthetic_never_reaches_for_a_live_source():
    """The offline setting exists to stay off the network."""
    from rainshield.ingest import build_providers

    assert [p.name for p in build_providers("synthetic")] == ["synthetic"]
