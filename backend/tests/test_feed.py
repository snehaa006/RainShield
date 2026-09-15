"""The arrival log, the per-region cache, and the live-feed API surface.

What matters here is that the feed is a *stream with provenance*: observations
arrive on a cadence, each one is recorded with the time it landed, and nothing
generated is ever presented as an observation.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("RAINSHIELD_PROVIDER", "synthetic")

from fastapi.testclient import TestClient  # noqa: E402

import rainshield.ingest as ingest  # noqa: E402
from rainshield.api.app import app  # noqa: E402
from rainshield.config import LEAD_TIMES  # noqa: E402
from rainshield.regions import PRIMARY_REGION_ID, SIMULATED_REGION_ID  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean():
    ingest.clear_cache()
    ingest.clear_feed_log()
    yield
    ingest.clear_cache()
    ingest.clear_feed_log()


# -- cache and log ---------------------------------------------------------


def test_each_region_is_cached_separately():
    primary = ingest.get_observation(region_id=PRIMARY_REGION_ID)
    simulated = ingest.get_observation(region_id=SIMULATED_REGION_ID)
    assert primary.region_id == PRIMARY_REGION_ID
    assert simulated.region_id == SIMULATED_REGION_ID
    # Fetching one must not evict or overwrite the other.
    assert ingest.get_observation(region_id=PRIMARY_REGION_ID) is primary


def test_clearing_one_region_leaves_the_other_cached():
    primary = ingest.get_observation(region_id=PRIMARY_REGION_ID)
    simulated = ingest.get_observation(region_id=SIMULATED_REGION_ID)
    ingest.clear_cache(SIMULATED_REGION_ID)
    assert ingest.get_observation(region_id=PRIMARY_REGION_ID) is primary
    assert ingest.get_observation(region_id=SIMULATED_REGION_ID) is not simulated


def test_arrivals_are_logged_per_region():
    ingest.get_observation(region_id=PRIMARY_REGION_ID)
    ingest.get_observation(region_id=SIMULATED_REGION_ID)

    primary_log = ingest.feed_log(PRIMARY_REGION_ID)
    simulated_log = ingest.feed_log(SIMULATED_REGION_ID)
    assert len(primary_log) == 1
    assert len(simulated_log) == 1
    assert simulated_log[0].simulated is True
    assert simulated_log[0].peak_rain_3h >= 0


def test_log_records_one_entry_per_fresh_fetch_not_per_read():
    ingest.get_observation(region_id=SIMULATED_REGION_ID)
    for _ in range(4):
        ingest.get_observation(region_id=SIMULATED_REGION_ID)  # served from cache
    assert len(ingest.feed_log(SIMULATED_REGION_ID)) == 1

    ingest.get_observation(force_refresh=True, region_id=SIMULATED_REGION_ID)
    assert len(ingest.feed_log(SIMULATED_REGION_ID)) == 2


def test_log_is_bounded():
    for _ in range(ingest.FEED_LOG_LIMIT + 8):
        ingest.get_observation(force_refresh=True, region_id=SIMULATED_REGION_ID)
    assert len(ingest.feed_log(SIMULATED_REGION_ID)) == ingest.FEED_LOG_LIMIT


def test_simulated_region_never_reaches_for_a_live_provider():
    """A generated region must not be able to attribute its output to an
    upstream, whatever RAINSHIELD_PROVIDER says."""
    providers = ingest.build_providers("openmeteo", region_id=SIMULATED_REGION_ID)
    assert [p.name for p in providers] == ["simulated-storm"]


def test_simulated_cadence_defaults_to_the_live_cadence(monkeypatch):
    monkeypatch.delenv("RAINSHIELD_SIM_CADENCE", raising=False)
    assert ingest.simulated_cadence() == ingest.SETTINGS.cache_ttl
    assert ingest.cadence_for(SIMULATED_REGION_ID) == ingest.SETTINGS.cache_ttl


def test_simulated_cadence_can_be_overridden(monkeypatch):
    monkeypatch.setenv("RAINSHIELD_SIM_CADENCE", "30")
    assert ingest.simulated_cadence() == 30
    monkeypatch.setenv("RAINSHIELD_SIM_CADENCE", "nonsense")
    assert ingest.simulated_cadence() == ingest.SETTINGS.cache_ttl


# -- API -------------------------------------------------------------------


def test_regions_endpoint_lists_both(client):
    body = client.get("/api/regions").json()
    ids = [r["id"] for r in body["regions"]]
    assert body["default"] == PRIMARY_REGION_ID
    assert ids[0] == PRIMARY_REGION_ID
    assert SIMULATED_REGION_ID in ids
    simulated = next(r for r in body["regions"] if r["id"] == SIMULATED_REGION_ID)
    assert simulated["simulated"] is True
    assert simulated["kind"] == "simulated"
    assert simulated["timezone"]


def test_unknown_region_is_a_404(client):
    for path in ("/api/region", "/api/forecast", "/api/series", "/api/observation"):
        assert client.get(path, params={"region": "atlantis"}).status_code == 404


def test_forecast_is_scoped_to_its_region(client):
    primary = client.get("/api/forecast", params={"lead": 0}).json()
    simulated = client.get(
        "/api/forecast", params={"lead": 0, "region": SIMULATED_REGION_ID}
    ).json()

    assert primary["region"]["id"] == PRIMARY_REGION_ID
    assert simulated["region"]["id"] == SIMULATED_REGION_ID
    assert simulated["observation"]["simulated"] is True
    # A simulated region reports where its storm is; a live one has no phase.
    assert primary["storm"] is None
    assert set(simulated["storm"]) == {"phase", "label"}


def test_observation_endpoint_carries_every_field(client):
    body = client.get("/api/observation", params={"region": SIMULATED_REGION_ID}).json()

    observed = {f["key"] for f in body["fields"]["observed"]}
    assert observed == {"rainRate", "rain3h", "soilMoisture", "cloudCover", "antecedent24h"}
    derived = {f["key"] for f in body["fields"]["derived"]}
    assert derived == {"river_level", "cloud_top_temp", "radar_reflectivity"}
    statics = {f["key"] for f in body["fields"]["static"]}
    assert statics == {"elevation", "slope", "infrastructure", "population"}

    for group in body["fields"].values():
        for field in group:
            assert field["unit"]
            assert field["description"]
            assert field["min"] <= field["mean"] <= field["max"]

    # Every model channel is accounted for somewhere in the payload.
    assert set(body["channelOrder"]) >= set(body["dynamicChannels"])


def test_rain_fields_report_every_lead_time(client):
    body = client.get("/api/observation", params={"region": SIMULATED_REGION_ID}).json()
    for field in body["fields"]["observed"]:
        if field["key"] in {"rainRate", "rain3h"}:
            assert set(field["perLead"]) == {str(lead) for lead in LEAD_TIMES}
        else:
            assert field["perLead"] is None


def test_timestamps_carry_both_zones(client):
    body = client.get("/api/observation", params={"region": SIMULATED_REGION_ID}).json()
    stamp = body["observation"]["timestamp"]
    assert stamp["timezone"] == "Asia/Kolkata"
    assert stamp["utcOffset"] == "+05:30"
    assert stamp["abbreviation"] == "IST"
    assert stamp["utc"].endswith("+00:00")

    utc = datetime.fromisoformat(stamp["utc"])
    local = datetime.fromisoformat(stamp["local"])
    assert utc == local  # same instant, different rendering
    assert local.utcoffset() == timedelta(hours=5, minutes=30)


def test_next_update_is_one_cadence_after_the_observation(client):
    body = client.get("/api/observation", params={"region": SIMULATED_REGION_ID}).json()
    observation = body["observation"]
    gap = observation["nextUpdate"]["epoch"] - observation["timestamp"]["epoch"]
    assert gap == pytest.approx(observation["cadenceSeconds"], abs=1)


def test_observation_lists_arrivals_oldest_first(client):
    client.post("/api/refresh", params={"region": SIMULATED_REGION_ID})
    client.post("/api/refresh", params={"region": SIMULATED_REGION_ID})
    body = client.get("/api/observation", params={"region": SIMULATED_REGION_ID}).json()

    arrivals = body["arrivals"]
    assert len(arrivals) >= 2
    stamps = [a["timestamp"]["epoch"] for a in arrivals]
    assert stamps == sorted(stamps)
    assert all(a["simulated"] for a in arrivals)


def test_health_reports_every_region(client):
    body = client.get("/health").json()
    assert set(body["feeds"]) == {PRIMARY_REGION_ID, SIMULATED_REGION_ID}
    assert body["feeds"][SIMULATED_REGION_ID]["simulated"] is True
    assert body["simulatedCadence"] > 0


def test_refresh_only_touches_the_named_region(client):
    client.get("/api/forecast", params={"lead": 0})
    before = ingest.get_observation(region_id=PRIMARY_REGION_ID)
    client.post("/api/refresh", params={"region": SIMULATED_REGION_ID})
    assert ingest.get_observation(region_id=PRIMARY_REGION_ID) is before


def test_auto_and_unknown_providers_fall_back_to_the_default_order():
    """`auto` is set in the deployed Render blueprint. It used to work only
    because an unrecognised name left the sort untouched; it is now explicit."""
    default = [p.name for p in ingest.build_providers("openmeteo")]
    assert [p.name for p in ingest.build_providers("auto")] == default
    assert [p.name for p in ingest.build_providers("typo")] == default
    # A blank-but-present setting (RAINSHIELD_PROVIDER="  ") is a preference of
    # nothing, not a request for the synthetic feed.
    assert [p.name for p in ingest.build_providers("  ")] == default
    # A real preference still reorders.
    assert [p.name for p in ingest.build_providers("metno")][0] == "metno"
