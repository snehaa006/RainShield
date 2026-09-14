"""Live observation providers and the TTL cache in front of them."""

from __future__ import annotations

import logging
import threading

from rainshield.config import SETTINGS
from rainshield.ingest.base import LiveObservation
from rainshield.ingest.openmeteo import OpenMeteoProvider
from rainshield.ingest.synthetic import SyntheticProvider

log = logging.getLogger(__name__)

_lock = threading.Lock()
_cached: LiveObservation | None = None


def build_provider(name: str | None = None):
    chosen = (name or SETTINGS.provider).lower()
    if chosen == "synthetic":
        return SyntheticProvider()
    return OpenMeteoProvider()


def get_observation(force_refresh: bool = False) -> LiveObservation:
    """Return the current observation, refetching when the cache has expired.

    On upstream failure the last good observation is reused if there is one;
    otherwise the synthetic provider fills in. Either way the result is flagged
    degraded so the UI can say so rather than silently showing stale numbers.
    """
    global _cached

    with _lock:
        cached = _cached
        if not force_refresh and cached is not None and cached.age_seconds() < SETTINGS.cache_ttl:
            return cached

    provider = build_provider()
    try:
        observation = provider.fetch()
    except Exception as exc:  # noqa: BLE001 — any upstream failure degrades gracefully
        log.warning("live fetch from %s failed: %s", provider.name, exc)
        reason = f"{provider.name} unreachable: {type(exc).__name__}"
        if cached is not None:
            cached.degraded = True
            if reason not in cached.notes:
                cached.notes.append(f"serving cached data — {reason}")
            return cached
        observation = SyntheticProvider().fetch(reason=reason)

    with _lock:
        _cached = observation
    return observation


def clear_cache() -> None:
    global _cached
    with _lock:
        _cached = None


__all__ = [
    "LiveObservation",
    "OpenMeteoProvider",
    "SyntheticProvider",
    "build_provider",
    "clear_cache",
    "get_observation",
]
