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
