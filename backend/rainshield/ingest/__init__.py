"""Live observation providers, the fallback chain, and the TTL cache."""

from __future__ import annotations

import logging
import threading

from rainshield.config import SETTINGS
from rainshield.ingest.base import LiveObservation
from rainshield.ingest.metno import MetNoProvider
from rainshield.ingest.openmeteo import OpenMeteoProvider
from rainshield.ingest.synthetic import SyntheticProvider

log = logging.getLogger(__name__)

_lock = threading.Lock()
_cached: LiveObservation | None = None


#: Live sources in default preference order. Open-Meteo first — it matches the
#: Stage 0 feeds and serves the whole mesh in one request. MET Norway second:
#: Open-Meteo's free tier is capped per IP and on shared hosting that quota can
#: be spent by another tenant before this service calls it at all, so the second
#: source has to be genuinely independent rather than a retry of the first.
LIVE_PROVIDERS = {"openmeteo": OpenMeteoProvider, "metno": MetNoProvider}


def build_providers(name: str | None = None) -> list:
    """The live providers to try, in order.

    RAINSHIELD_PROVIDER names the *preferred* source, not the only one: the
    remaining live sources still follow it as fallbacks, because a named
    preference losing its upstream should not mean serving invented data.
    "synthetic" is the one strict setting — it exists to keep the service off
    the network, so it must never silently reach for a live source.
    """
    chosen = (name or SETTINGS.provider).lower()
    if chosen == "synthetic":
        return [SyntheticProvider()]

    ordered = sorted(LIVE_PROVIDERS, key=lambda n: n != chosen)
    return [LIVE_PROVIDERS[n]() for n in ordered]


def get_observation(force_refresh: bool = False) -> LiveObservation:
    """Return the current observation, refetching when the cache has expired.

    Providers are tried in order. If they all fail the last good observation is
    reused; if there is none, the synthetic provider fills in. Anything that is
    not a fresh live fetch is flagged degraded so the UI can say so rather than
    silently presenting stale or invented numbers as live.
    """
    global _cached

    with _lock:
        cached = _cached
        if not force_refresh and cached is not None and cached.age_seconds() < SETTINGS.cache_ttl:
            return cached

    failures: list[str] = []
    for provider in build_providers():
        try:
            observation = provider.fetch()
        except Exception as exc:  # noqa: BLE001 — any upstream failure tries the next source
            log.warning("live fetch from %s failed: %s", provider.name, exc)
            failures.append(f"{provider.name}: {exc}")
            continue

        if failures:
            observation.notes.append(f"after {len(failures)} source(s) failed")
        with _lock:
            _cached = observation
        return observation

    reason = "; ".join(failures) or "no provider available"
    if cached is not None:
        cached.degraded = True
        note = f"serving cached data — every live source failed ({reason})"
        if note not in cached.notes:
            cached.notes.append(note)
        return cached

    observation = SyntheticProvider().fetch(reason=f"every live source failed — {reason}")
    with _lock:
        _cached = observation
    return observation


def clear_cache() -> None:
    global _cached
    with _lock:
        _cached = None


__all__ = [
    "LiveObservation",
    "MetNoProvider",
    "OpenMeteoProvider",
    "SyntheticProvider",
    "build_providers",
    "clear_cache",
    "get_observation",
]
