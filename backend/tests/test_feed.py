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
    # Also drop any in-flight refresh: a test that deliberately hangs one would
    # otherwise hand its gate to the next test.
    ingest.clear_cache()
    ingest.clear_feed_log()
    ingest.clear_inflight()
    yield
    ingest.clear_cache()
    ingest.clear_feed_log()
    ingest.clear_inflight()


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


# -- single-flight and bounded waits ---------------------------------------


def test_concurrent_callers_share_one_fetch(monkeypatch):
    """The dashboard asks for the forecast and the trend in parallel while the
    warm-up thread runs, so an unguarded cold cache walked the provider chain
    three times at once — against an upstream that rate-limits per IP."""
    import threading
    import time

    calls = []

    class _Slow:
        name = "slow"

        def fetch(self):
            calls.append(time.monotonic())
            time.sleep(0.4)
            return ingest.SyntheticProvider(region_id=PRIMARY_REGION_ID).fetch()

    monkeypatch.setattr(ingest, "build_providers", lambda *a, **k: [_Slow()])

    results = []
    threads = [
        threading.Thread(
            target=lambda: results.append(
                ingest.get_observation(region_id=PRIMARY_REGION_ID, budget=5)
            )
        )
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1, f"expected one upstream fetch, got {len(calls)}"
    assert len(results) == 4
    assert all(r is not None for r in results)


def test_a_slow_upstream_does_not_hold_the_request_open(monkeypatch):
    """A feed that never answers should make the board older, not make it hang."""
    import time

    class _Hanging:
        name = "hanging"

        def fetch(self):
            time.sleep(30)
            raise AssertionError("should not be waited on")

    monkeypatch.setattr(ingest, "build_providers", lambda *a, **k: [_Hanging()])

    started = time.monotonic()
    observation = ingest.get_observation(region_id=PRIMARY_REGION_ID, budget=0.5)
    elapsed = time.monotonic() - started

    assert elapsed < 5, f"request blocked for {elapsed:.1f}s"
    # Nothing was cached, so a labelled synthetic field stands in rather than a
    # spinner that never resolves.
    assert observation is not None
    assert observation.degraded is True


def test_a_slow_upstream_serves_the_previous_observation(monkeypatch):
    import time

    good = ingest.get_observation(region_id=PRIMARY_REGION_ID)

    class _Hanging:
        name = "hanging"

        def fetch(self):
            time.sleep(30)
            raise AssertionError("should not be waited on")

    monkeypatch.setattr(ingest, "build_providers", lambda *a, **k: [_Hanging()])

    served = ingest.get_observation(force_refresh=True, region_id=PRIMARY_REGION_ID, budget=0.5)
    assert served.fetched_at == good.fetched_at
    assert served.degraded is True
    assert any("upstream slow" in note for note in served.notes)


# --------------------------------------------------------------------------
# Scoring off the request path
# --------------------------------------------------------------------------


def test_precompute_scores_every_lead_time():
    """After a precompute, no lead time may still need the network."""
    from rainshield import service
    from rainshield.config import LEAD_TIMES
    from rainshield.ingest import get_observation

    service._SUSCEPTIBILITY_CACHE.clear()
    observation = get_observation(region_id=PRIMARY_REGION_ID)
    service.precompute(observation)

    stamp = observation.fetched_at.isoformat()
    for lead in LEAD_TIMES:
        assert (observation.region_id, stamp, lead) in service._SUSCEPTIBILITY_CACHE


def test_precompute_leaves_no_model_call_for_the_request(monkeypatch):
    """The point of it: a scored observation makes the request path cheap.

    Asserted by counting forward passes rather than by timing, because a
    timing ratio is both flaky and order-dependent. Seven passes is about
    7.5 CPU-seconds, which on an instance capped at 0.15 of a core is most of
    a minute landing on whoever loads the page first.

    The assertion that carries the meaning is the warm one — after a
    precompute the request must make *no* model call at all. The cold case is
    only a control, and it is asserted loosely on purpose: scoring now happens
    on a background thread, so a scorer may legitimately be running alongside
    and inflate the count. Pinning it exactly would be testing thread
    scheduling, not behaviour.
    """
    from rainshield import service
    from rainshield.config import LEAD_TIMES
    from rainshield.hazard import DEFAULT_WHAT_IF
    from rainshield.ingest import get_observation

    calls: list[int] = []
    real = service.predict_susceptibility

    def counted(observation, lead, region_id):
        calls.append(lead)
        return real(observation, lead, region_id)

    monkeypatch.setattr(service, "predict_susceptibility", counted)

    observation = get_observation(region_id=PRIMARY_REGION_ID)

    # Cold: the series endpoint has to score the leads itself.
    service._SUSCEPTIBILITY_CACHE.clear()
    calls.clear()
    service.series_payload(DEFAULT_WHAT_IF, PRIMARY_REGION_ID)
    assert set(calls) >= set(LEAD_TIMES), (
        f"cold request should have scored every lead, got {sorted(set(calls))}"
    )

    # Warm: precompute has already done it, so the request does none.
    service._SUSCEPTIBILITY_CACHE.clear()
    service.precompute(observation)
    calls.clear()
    service.series_payload(DEFAULT_WHAT_IF, PRIMARY_REGION_ID)
    assert calls == [], f"request still ran the network for leads {calls}"


def test_subscribers_are_notified_when_an_observation_lands():
    """The hook the scoring rides on must actually fire."""
    from rainshield.ingest import (
        clear_cache,
        clear_observation_subscribers,
        get_observation,
        on_observation,
    )

    seen: list[str] = []
    try:
        on_observation(lambda obs: seen.append(obs.region_id))
        clear_cache(PRIMARY_REGION_ID)
        get_observation(region_id=PRIMARY_REGION_ID, force_refresh=True)
        assert PRIMARY_REGION_ID in seen
    finally:
        clear_observation_subscribers()


def test_a_slow_subscriber_never_delays_the_feed():
    """The regression that took the deployed board down.

    `_record` runs inside the provider chain, which runs before the gate that
    releases every request waiting on that refresh. When the scoring subscriber
    ran inline it held that gate shut for ~7.5 CPU-seconds per region — most of
    a minute on a 0.15-core instance — and the dashboard sat on "Loading live
    forecast" until it timed out. Subscribers are dispatched on their own
    thread so that no subscriber can do that again, however careless.
    """
    import time

    from rainshield.ingest import (
        clear_cache,
        clear_observation_subscribers,
        get_observation,
        on_observation,
    )

    ran: list[str] = []
    delay = 3.0

    def slow(observation):
        time.sleep(delay)
        ran.append(observation.region_id)

    try:
        on_observation(slow)
        clear_cache(PRIMARY_REGION_ID)
        started = time.perf_counter()
        get_observation(region_id=PRIMARY_REGION_ID, force_refresh=True)
        elapsed = time.perf_counter() - started

        assert elapsed < delay / 2, (
            f"the feed waited {elapsed:.2f}s on a subscriber — it must not"
        )

        # It still runs; it just runs beside the feed rather than inside it.
        deadline = time.perf_counter() + delay * 3
        while not ran and time.perf_counter() < deadline:
            time.sleep(0.05)
        assert ran == [PRIMARY_REGION_ID]
    finally:
        clear_observation_subscribers()


def test_a_failing_subscriber_never_costs_the_feed_an_observation():
    """A precompute that blows up must not take the arrival down with it."""
    from rainshield.ingest import (
        clear_cache,
        clear_observation_subscribers,
        get_observation,
        on_observation,
    )

    def explode(_observation):
        raise RuntimeError("scoring failed")

    try:
        on_observation(explode)
        clear_cache(PRIMARY_REGION_ID)
        observation = get_observation(region_id=PRIMARY_REGION_ID, force_refresh=True)
        assert observation is not None
        assert observation.region_id == PRIMARY_REGION_ID
    finally:
        clear_observation_subscribers()
