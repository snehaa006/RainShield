"""Alert lifecycle: detection, de-duplication and legal state transitions."""

import pytest

from rainshield import alerting


@pytest.fixture(autouse=True)
def clean_store():
    """The alert store is process-global; isolate every test from the others."""
    alerting._store.clear()
    alerting._audit.clear()
    yield
    alerting._store.clear()
    alerting._audit.clear()


def payload(**ward):
    base = {
        "id": "w1",
        "tier": "CRITICAL",
        "risk": 0.9,
        "peakFloodProbability": 0.95,
        "peakWaterDepth": 1.7,
        "timeToInundation": 30,
    }
    base.update(ward)
    return {"region": {"id": "r1", "name": "Test"}, "wards": [base], "isSimulating": False}


def test_critical_ward_drafts_an_alert_under_review():
    created = alerting.evaluate_forecast(payload())
    assert len(created) == 1
    assert created[0]["status"] == "UNDER_REVIEW"
    assert created[0]["tier"] == "CRITICAL"
    assert created[0]["reason"]


def test_sub_critical_ward_raises_nothing():
    assert alerting.evaluate_forecast(payload(tier="WARNING", risk=0.4, peakFloodProbability=0.3, peakWaterDepth=0.2)) == []


def test_repeat_forecast_does_not_duplicate_an_open_alert():
    alerting.evaluate_forecast(payload())
    assert alerting.evaluate_forecast(payload()) == []
    assert len(alerting.list_alerts("r1")) == 1


def test_resolved_alert_allows_a_fresh_one_for_the_same_ward():
    alert_id = alerting.evaluate_forecast(payload())[0]["id"]
    for status in ("APPROVED", "BROADCASTING", "ACTIVE", "RESOLVED"):
        alerting.transition(alert_id, status)
    assert len(alerting.evaluate_forecast(payload())) == 1


def test_broadcast_reports_channel_delivery():
    alert_id = alerting.evaluate_forecast(payload())[0]["id"]
    alerting.transition(alert_id, "APPROVED")
    assert set(alerting.transition(alert_id, "BROADCASTING")["channels"]) == {"sms", "app", "web", "api", "siren"}


@pytest.mark.parametrize(
    "path, blocked",
    [
        ([], "ACTIVE"),          # cannot broadcast without review
        (["APPROVED"], "RESOLVED"),
        (["APPROVED", "BROADCASTING", "ACTIVE"], "CANCELLED"),
    ],
)
def test_illegal_transitions_are_rejected(path, blocked):
    alert_id = alerting.evaluate_forecast(payload())[0]["id"]
    for status in path:
        alerting.transition(alert_id, status)
    with pytest.raises(ValueError):
        alerting.transition(alert_id, blocked)


def test_unknown_alert_id_raises_key_error():
    with pytest.raises(KeyError):
        alerting.transition("RS-does-not-exist", "APPROVED")


def test_audit_trail_records_every_transition():
    alert_id = alerting.evaluate_forecast(payload())[0]["id"]
    alerting.transition(alert_id, "APPROVED")
    events = [entry["event"] for entry in alerting.audit_log()]
    assert events == ["ALERT_APPROVED", "ALERT_AUTO_DRAFTED"]
    assert all(entry["alertId"] == alert_id for entry in alerting.audit_log())


def test_region_filter_scopes_the_listing():
    alerting.evaluate_forecast(payload())
    other = payload()
    other["region"] = {"id": "r2", "name": "Other"}
    alerting.evaluate_forecast(other)
    assert len(alerting.list_alerts("r1")) == 1
    assert len(alerting.list_alerts()) == 2
