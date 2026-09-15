"""Operational alert orchestration for the RainShield prototype.

The forecast/risk engine remains the source of truth. This module turns a
critical ward-level threshold crossing into an incident-like alert record,
keeps a small in-memory audit trail, and exposes lifecycle transitions to the
API layer. Production deployment should replace the in-memory store with a
transactional database and an authenticated authority gateway.
"""
from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

CRITICAL_PROBABILITY = 0.90
CRITICAL_DEPTH = 1.50
CRITICAL_RISK = 0.75

_store: dict[str, dict[str, Any]] = {}
_audit: list[dict[str, Any]] = []
_lock = RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _severity(ward: dict[str, Any]) -> str:
    if (
        ward.get("tier") == "CRITICAL"
        or float(ward.get("peakFloodProbability", 0)) >= CRITICAL_PROBABILITY
        or float(ward.get("peakWaterDepth", 0)) >= CRITICAL_DEPTH
        or float(ward.get("risk", 0)) >= CRITICAL_RISK
    ):
        return "CRITICAL"
    if ward.get("tier") == "WARNING" or float(ward.get("risk", 0)) >= 0.50:
        return "WARNING"
    if ward.get("tier") == "WATCH" or float(ward.get("risk", 0)) >= 0.25:
        return "WATCH"
    return "NORMAL"


def _reasons(ward: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    probability = float(ward.get("peakFloodProbability", 0))
    depth = float(ward.get("peakWaterDepth", 0))
    onset = ward.get("timeToInundation")
    if probability >= CRITICAL_PROBABILITY:
        reasons.append(f"Flood probability reached {probability * 100:.0f}%")
    if depth >= CRITICAL_DEPTH:
        reasons.append(f"Expected depth reached {depth:.2f} m")
    if onset is not None and int(onset) <= 60:
        reasons.append(f"Inundation onset estimated within {int(onset)} min")
    if not reasons:
        reasons.append("Composite risk crossed the critical threshold")
    return reasons


def _record(event: str, alert: dict[str, Any], detail: str) -> None:
    _audit.insert(0, {"id": uuid4().hex[:12], "timestamp": _now(), "event": event, "alertId": alert["id"], "detail": detail})
    del _audit[100:]


def evaluate_forecast(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Create alerts for newly critical wards in one forecast response."""
    created: list[dict[str, Any]] = []
    region = payload.get("region", {})
    region_id = region.get("id", "unknown")
    with _lock:
        for ward in payload.get("wards", []):
            if _severity(ward) != "CRITICAL":
                continue
            key = f"{region_id}:{ward['id']}"
            existing = next((a for a in _store.values() if a["dedupeKey"] == key and a["status"] not in {"RESOLVED", "CANCELLED"}), None)
            if existing:
                existing["latestWard"] = ward
                existing["updatedAt"] = _now()
                continue

            created_at = _now()
            alert_id = f"RS-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8].upper()}"
            event = {
                "id": alert_id,
                "dedupeKey": key,
                "createdAt": created_at,
                "updatedAt": created_at,
                "status": "UNDER_REVIEW",
                "tier": "CRITICAL",
                "region": region,
                "ward": ward,
                "reason": _reasons(ward),
                "channels": {"sms": 0, "app": 0, "web": 0, "api": 0, "siren": 0},
                "simulation": bool(payload.get("isSimulating", False)),
            }
            _store[alert_id] = event
            _record("ALERT_AUTO_DRAFTED", event, "Critical threshold crossed by the forecast/risk engine")
            created.append(dict(event))
    return created


def list_alerts(region_id: str | None = None) -> list[dict[str, Any]]:
    with _lock:
        values = list(_store.values())
        if region_id:
            values = [a for a in values if a["region"].get("id") == region_id]
        return sorted((dict(a) for a in values), key=lambda a: a["createdAt"], reverse=True)


def get_alert(alert_id: str) -> dict[str, Any] | None:
    with _lock:
        alert = _store.get(alert_id)
        return dict(alert) if alert else None


def transition(alert_id: str, status: str) -> dict[str, Any]:
    allowed = {
        "UNDER_REVIEW": {"APPROVED", "CANCELLED"},
        "APPROVED": {"BROADCASTING", "CANCELLED"},
        "BROADCASTING": {"ACTIVE"},
        "ACTIVE": {"RESOLVED"},
        "RESOLVED": set(),
        "CANCELLED": set(),
    }
    with _lock:
        alert = _store.get(alert_id)
        if not alert:
            raise KeyError(alert_id)
        current = alert["status"]
        if status not in allowed.get(current, set()):
            raise ValueError(f"Cannot transition {current} → {status}")
        alert["status"] = status
        alert["updatedAt"] = _now()
        if status == "BROADCASTING":
            alert["channels"] = {"sms": 96, "app": 94, "web": 100, "api": 100, "siren": 88}
        _record(f"ALERT_{status}", alert, f"Lifecycle transition {current} → {status}")
        return dict(alert)


def audit_log() -> list[dict[str, Any]]:
    with _lock:
        return list(_audit)
