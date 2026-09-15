"""End-to-end API contract, driven against the deterministic synthetic feed."""

import os

import pytest

os.environ.setdefault("RAINSHIELD_PROVIDER", "synthetic")

from fastapi.testclient import TestClient  # noqa: E402

from rainshield.api.app import app  # noqa: E402
from rainshield.config import LEAD_TIMES, REGION  # noqa: E402

CELL_COUNT = REGION.cell_count


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_reports_model_and_feed(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["model"]["backend"] in {"cnn-transformer", "analytical"}
    assert "source" in body["observation"]


def test_region_returns_every_static_layer(client):
    body = client.get("/api/region").json()

    assert body["region"]["rows"] == REGION.rows
    assert body["region"]["cols"] == REGION.cols
    assert len(body["wards"]) > 0
    for layer in ("lon", "lat", "elevation", "slope", "population", "infraProximity", "landUse", "wardIndex"):
        assert len(body["cells"][layer]) == CELL_COUNT, layer

    # Row 0 must be the northern edge.
    assert body["cells"]["lat"][0] > body["cells"]["lat"][-1]
    assert max(body["cells"]["wardIndex"]) < len(body["wards"])


@pytest.mark.parametrize("lead", LEAD_TIMES)
def test_forecast_shapes_for_every_lead(client, lead):
    body = client.get("/api/forecast", params={"lead": lead}).json()

    assert body["lead"] == lead
    for layer in ("risk", "floodProbability", "rainfallIntensity", "waterDepth", "timeToInundation"):
        assert len(body["cells"][layer]) == CELL_COUNT, layer

    assert all(0.0 <= v <= 1.0 for v in body["cells"]["risk"])
    assert all(0.0 <= v <= 1.0 for v in body["cells"]["floodProbability"])
    assert body["summary"]["tier"] in {"NORMAL", "WATCH", "WARNING", "CRITICAL"}
    assert body["confidence"] in {"LOW", "MEDIUM", "HIGH"}


def test_forecast_rejects_unknown_lead(client):
    assert client.get("/api/forecast", params={"lead": 45}).status_code == 422


def test_what_if_is_validated_and_applied(client):
    assert client.get("/api/forecast", params={"drainage_capacity": 9}).status_code == 422

    baseline = client.get("/api/forecast", params={"lead": 60}).json()
    flooded = client.get(
        "/api/forecast", params={"lead": 60, "extra_rainfall": 120, "drainage_capacity": 0.4}
    ).json()

    assert flooded["isSimulating"] is True
    assert baseline["isSimulating"] is False
    assert flooded["summary"]["peakRisk"] > baseline["summary"]["peakRisk"]


def test_series_covers_all_lead_times(client):
    body = client.get("/api/series").json()
    assert [p["lead"] for p in body["series"]] == list(LEAD_TIMES)


def test_cell_detail_and_bounds(client):
    body = client.get("/api/cell/10/12").json()
    assert body["cell"]["row"] == 10
    assert body["cell"]["col"] == 12
    assert body["cell"]["wardId"]
    assert len(body["series"]) == len(LEAD_TIMES)

    assert client.get(f"/api/cell/{REGION.rows}/0").status_code == 404
    assert client.get("/api/cell/0/-1").status_code == 404


def test_ward_rollup_is_ranked_and_complete(client):
    body = client.get("/api/forecast", params={"lead": 120}).json()
    wards = body["wards"]

    assert [w["risk"] for w in wards] == sorted((w["risk"] for w in wards), reverse=True)
    assert sum(w["cellCount"] for w in wards) == CELL_COUNT


# --------------------------------------------------------------------------
# Drainage and pumping
# --------------------------------------------------------------------------


def test_drainage_reports_catchments_stations_and_tide(client):
    body = client.get("/api/drainage?lead=60").json()

    assert body["lead"] == 60
    assert len(body["stations"]) == 7
    assert len(body["catchments"]) == 7
    assert len(body["cells"]["catchment"]) == CELL_COUNT
    assert len(body["cells"]["sea"]) == CELL_COUNT

    tide = body["tide"]
    assert tide["lowestAstronomicalMCd"] <= tide["levelMCd"] <= tide["highestAstronomicalMCd"]
    assert tide["phase"] in {"high", "low", "flooding", "ebbing"}

    totals = body["totals"]
    assert totals["catchmentCount"] == 7
    assert totals["installedPumpCumecs"] == pytest.approx(180.0)
    assert totals["pumpUnitCumecs"] == 6.0


def test_drainage_rejects_an_unknown_lead(client):
    assert client.get("/api/drainage?lead=7").status_code == 422


def test_drainage_rejects_an_unknown_region(client):
    assert client.get("/api/drainage?region=atlantis").status_code == 404


def test_drainage_rejects_an_impossible_tide(client):
    assert client.get("/api/drainage?tide=99").status_code == 422


def test_drainage_tide_override_is_flagged(client):
    pinned = client.get("/api/drainage?tide=4.5").json()
    assert pinned["tideOverridden"] is True
    assert pinned["tide"]["levelMCd"] == pytest.approx(4.5)
    assert pinned["isSimulating"] is True

    natural = client.get("/api/drainage").json()
    assert natural["tideOverridden"] is False


def test_drainage_high_tide_shuts_the_gates(client):
    low = client.get("/api/drainage?tide=0.5").json()
    high = client.get("/api/drainage?tide=4.5").json()

    assert all(not c["gateClosed"] for c in low["catchments"])
    assert all(c["gateClosed"] for c in high["catchments"])
    assert low["totals"]["supplyCumecs"] > high["totals"]["supplyCumecs"]
    # With every gate shut, supply is the pumps alone.
    assert high["totals"]["supplyCumecs"] == pytest.approx(
        high["totals"]["installedPumpCumecs"]
    )


def test_drainage_extra_rainfall_raises_the_deficit(client):
    dry = client.get("/api/drainage?tide=4.5").json()["totals"]
    wet = client.get("/api/drainage?tide=4.5&extra_rainfall=250").json()["totals"]
    assert wet["inflowCumecs"] > dry["inflowCumecs"]
    assert wet["deficitCumecs"] >= dry["deficitCumecs"]
    assert wet["extraPumpsRequired"] >= dry["extraPumpsRequired"]


def test_drainage_losing_pumps_cuts_supply(client):
    full = client.get("/api/drainage").json()["totals"]
    none = client.get("/api/drainage?pump_availability=0").json()["totals"]
    assert none["supplyCumecs"] < full["supplyCumecs"]


def test_drainage_unpumped_area_claims_no_capacity(client):
    body = client.get("/api/drainage").json()
    unpumped = body["unpumped"]
    assert unpumped is not None
    assert unpumped["supplyModelled"] is False
    assert unpumped["areaKm2"] > 0
    assert unpumped["stationId"] is None
    # It is reported, but never folded into the headline numbers.
    assert all(c["id"] != unpumped["id"] for c in body["catchments"])


def test_drainage_capacity_figures_carry_their_caveat(client):
    body = client.get("/api/drainage").json()
    assert "estimate" in body["caveat"].lower()
    for station in body["stations"]:
        assert station["capacityBasis"]
        assert "ESTIMATE" in station["capacityBasis"]


def test_region_serves_the_real_pumping_stations(client):
    """The map draws these, so they must be the surveyed ones, not invented."""
    stations = client.get("/api/region").json()["stations"]
    assert len(stations) == 7
    names = {s["name"] for s in stations}
    assert "Haji Ali" in names and "Mogra (Andheri)" in names
    for station in stations:
        assert station["generated"] is False
        assert "ESTIMATE" in station["capacityBasis"]


def test_drainage_works_for_the_simulated_region(client):
    body = client.get("/api/drainage?region=coromandel").json()
    assert body["region"]["simulated"] is True
    assert len(body["stations"]) == 3
    assert all(s["generated"] for s in body["stations"])
    assert all("GENERATED" in s["capacityBasis"] for s in body["stations"])


def test_drainage_does_not_disturb_the_hazard_model(client):
    """Stage A is additive: the forecast must be byte-identical either side."""
    before = client.get("/api/forecast?lead=60").json()["cells"]
    client.get("/api/drainage?lead=60&tide=4.5&extra_rainfall=200")
    after = client.get("/api/forecast?lead=60").json()["cells"]
    assert before == after


def test_forecast_reports_the_hazard_path(client):
    """The board must always be able to say which model served it."""
    solver = client.get("/api/forecast?lead=60").json()["solver"]
    assert solver["mode"] in {"heuristic", "physics"}
    assert solver["label"] and solver["note"]
    if solver["mode"] == "heuristic":
        assert solver["massConserving"] is False
        assert solver["massClosure"] is None
    else:
        assert solver["massConserving"] is True
        assert solver["massClosure"]["error"] < 1e-9
