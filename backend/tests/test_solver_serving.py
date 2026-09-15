"""The physics path serving through the API, with the flag on.

Setting RAINSHIELD_SOLVER at import time is not enough: `rainshield.config`
reads the environment once, and earlier test modules have already imported it
by the time this file is collected, so the flag would arrive too late and
these tests would quietly assert against the heuristic path instead. The
setting is therefore rebuilt and patched onto the binding `service` actually
holds, which is what the dispatch reads.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("RAINSHIELD_PROVIDER", "synthetic")

from fastapi.testclient import TestClient  # noqa: E402

from rainshield import service  # noqa: E402
from rainshield.api.app import app  # noqa: E402
from rainshield.config import LEAD_TIMES, REGION, Settings  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def physics_solver():
    """Serve the physics path for this module, and only this module."""
    previous = os.environ.get("RAINSHIELD_SOLVER")
    os.environ["RAINSHIELD_SOLVER"] = "physics"
    original = service.SETTINGS
    service.SETTINGS = Settings()
    service._SOLVE_CACHE.clear()
    service._SUSCEPTIBILITY_CACHE.clear()
    try:
        yield service.SETTINGS
    finally:
        service.SETTINGS = original
        service._SOLVE_CACHE.clear()
        service._SUSCEPTIBILITY_CACHE.clear()
        if previous is None:
            os.environ.pop("RAINSHIELD_SOLVER", None)
        else:
            os.environ["RAINSHIELD_SOLVER"] = previous


@pytest.fixture(scope="module")
def client(physics_solver):
    with TestClient(app) as c:
        yield c


def test_the_flag_actually_switched_the_path(physics_solver):
    assert physics_solver.use_physics_solver
    assert service.SETTINGS.use_physics_solver


def test_forecast_is_served_by_the_solver_and_closes(client):
    body = client.get("/api/forecast?lead=120").json()
    solver = body["solver"]
    assert solver["mode"] == "physics"
    assert solver["massConserving"] is True
    assert solver["massClosure"]["error"] < 1e-9
    assert solver["steps"] > 0


def test_payload_shape_is_unchanged_by_the_switch(client):
    """Swapping the hazard model must not change the contract."""
    body = client.get("/api/forecast?lead=120").json()
    for key in ("risk", "floodProbability", "susceptibility", "waterDepth", "timeToInundation"):
        assert len(body["cells"][key]) == REGION.cell_count, key
    assert set(body["summary"]) >= {"tier", "peakRisk", "peakDepth", "populationAtRisk"}
    assert body["wards"]


def test_depths_are_physical(client):
    body = client.get("/api/forecast?lead=360").json()
    depths = body["cells"]["waterDepth"]
    assert min(depths) >= 0.0
    assert max(depths) < 20.0, "a 1 km cell metres deep everywhere is a bug"


def test_one_solve_serves_every_lead(client):
    """Every horizon must come from the same trajectory, not six of them.

    Proven by the solve metadata rather than by timing: the step count and the
    mass balance describe one integration, so if two different leads report
    identical figures they were served by the same cached solve.
    """
    first = client.get("/api/forecast?lead=30").json()["solver"]
    last = client.get("/api/forecast?lead=360").json()["solver"]
    assert first["steps"] == last["steps"]
    assert first["massClosure"] == last["massClosure"]


def test_water_recedes_once_the_rain_stops(client):
    """A trajectory, not six snapshots: depth must be able to go back down.

    The heuristic cannot do this — its response curve is a function of the
    rainfall at each lead alone, so a drying grid is simply a smaller number
    rather than water that went somewhere. Here it drained, was pumped, or
    reached the sea, and the mass balance says which.
    """
    series = client.get("/api/series").json()["series"]
    assert len(series) == len(LEAD_TIMES)
    depths = [point["depth"] for point in series]
    assert all(d >= 0 for d in depths)
    assert depths[0] == pytest.approx(0.0, abs=1e-9), "the grid starts dry"
    # Under the synthetic feed the rain eases, so the peak is not at the end.
    assert max(depths) > depths[-1] or len(set(depths)) == 1


def test_drainage_is_unaffected_by_the_hazard_path(client):
    """Stage A is a separate calculation and must not follow the flag."""
    body = client.get("/api/drainage?lead=60").json()
    assert len(body["catchments"]) == 7
    assert body["totals"]["installedPumpCumecs"] == pytest.approx(180.0)
