"""Live observation providers, the fallback chain, the TTL cache and the feed log.

Observations are cached per region. A live region walks its provider chain and
degrades to cached-then-synthetic data when every upstream fails; a simulated
region is driven by its own generator and never touches the network.

Every fresh observation is also appended to a bounded arrival log, which is what
backs the dashboard's live-feed view: it is the record of data actually landing,
with the time it landed and what was in it.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

from rainshield.config import SETTINGS
from rainshield.ingest.base import LiveObservation
from rainshield.ingest.metno import MetNoProvider
from rainshield.ingest.openmeteo import OpenMeteoProvider
from rainshield.ingest.simulated import SimulatedStormProvider, phase_at, phase_label
from rainshield.ingest.synthetic import SyntheticProvider
from rainshield.regions import PRIMARY_REGION_ID, get_region, region_ids

log = logging.getLogger(__name__)

_lock = threading.Lock()
_cached: dict[str, LiveObservation] = {}

#: How many arrivals to keep per region. At the default 600 s cadence this is
#: a little over four hours of history, which is all the feed view plots.
FEED_LOG_LIMIT = 48

_feed_log: dict[str, deque] = {}


#: Live sources in default preference order. Open-Meteo first — it matches the
#: Stage 0 feeds and serves the whole mesh in one request. MET Norway second:
#: Open-Meteo's free tier is capped per IP and on shared hosting that quota can
#: be spent by another tenant before this service calls it at all, so the second
#: source has to be genuinely independent rather than a retry of the first.
LIVE_PROVIDERS = {"openmeteo": OpenMeteoProvider, "metno": MetNoProvider}


def simulated_cadence() -> int:
    """Seconds between simulated observations.

    Defaults to the live feed's cache TTL, so the simulated region delivers on
    the same rhythm the real one does rather than on a rhythm of its own.
    """
    raw = os.getenv("RAINSHIELD_SIM_CADENCE")
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            log.warning("ignoring invalid RAINSHIELD_SIM_CADENCE=%r", raw)
    return SETTINGS.cache_ttl


def cadence_for(region_id: str) -> int:
    """Seconds an observation for this region stays current."""
    return simulated_cadence() if get_region(region_id).simulated else SETTINGS.cache_ttl


def build_providers(name: str | None = None, region_id: str = PRIMARY_REGION_ID) -> list:
    """The providers to try for a region, in order.

    A simulated region has exactly one source — its generator — and never falls
    through to a live one, so nothing invented can be attributed to an upstream.

    For a live region, RAINSHIELD_PROVIDER names the *preferred* source, not the
    only one: the remaining live sources still follow it as fallbacks, because a
    named preference losing its upstream should not mean serving invented data.
    "synthetic" is the one strict setting — it exists to keep the service off the
    network, so it must never silently reach for a live source.
    """
    if get_region(region_id).simulated:
        return [SimulatedStormProvider(region_id)]

    chosen = (name or SETTINGS.provider).strip().lower()
    if chosen == "synthetic":
        return [SyntheticProvider(region_id=region_id)]

    # "auto" means "no preference, use the default order". It was already being
    # set in the deployed Render blueprint and happened to work only because an
    # unrecognised name leaves the stable sort below untouched — worth naming
    # rather than leaving as an accident that a sort-key change would break.
    if chosen in {"auto", ""}:
        return [LIVE_PROVIDERS[n]() for n in LIVE_PROVIDERS]

    if chosen not in LIVE_PROVIDERS:
        log.warning(
            "RAINSHIELD_PROVIDER=%r is not a known source (%s); using the default order",
            chosen,
            ", ".join(sorted(LIVE_PROVIDERS)),
        )
        return [LIVE_PROVIDERS[n]() for n in LIVE_PROVIDERS]

    ordered = sorted(LIVE_PROVIDERS, key=lambda n: n != chosen)
    return [LIVE_PROVIDERS[n]() for n in ordered]


# --------------------------------------------------------------------------
# Arrival log
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FeedArrival:
    """One observation landing, as the live-feed view reports it."""

    region_id: str
    source: str
    fetched_at: datetime
    degraded: bool
    simulated: bool
    peak_rain_rate: float
    mean_rain_rate: float
    peak_rain_3h: float
    peak_soil_moisture: float
    mean_cloud_cover: float
    peak_antecedent_24h: float
    notes: tuple[str, ...] = field(default=())


def _record(observation: LiveObservation) -> None:
    """Append an arrival to the region's log, newest last."""
    rate, accum = observation.rain_rate[0], observation.rain_3h[0]
    arrival = FeedArrival(
        region_id=observation.region_id,
        source=observation.source,
        fetched_at=observation.fetched_at,
        degraded=observation.degraded,
        simulated=observation.simulated,
        peak_rain_rate=round(float(rate.max()), 2),
        mean_rain_rate=round(float(rate.mean()), 2),
        peak_rain_3h=round(float(accum.max()), 2),
        peak_soil_moisture=round(float(observation.soil_moisture.max()), 3),
        mean_cloud_cover=round(float(observation.cloud_cover.mean()), 1),
        peak_antecedent_24h=round(float(observation.antecedent_24h.max()), 2),
        notes=tuple(observation.notes),
    )
    with _lock:
        bucket = _feed_log.setdefault(observation.region_id, deque(maxlen=FEED_LOG_LIMIT))
        bucket.append(arrival)


def feed_log(region_id: str = PRIMARY_REGION_ID) -> list[FeedArrival]:
    """Arrivals for a region, oldest first."""
    with _lock:
        return list(_feed_log.get(region_id, ()))


def clear_feed_log() -> None:
    with _lock:
        _feed_log.clear()


# --------------------------------------------------------------------------
# Fetch + cache
# --------------------------------------------------------------------------


def get_observation(
    force_refresh: bool = False, region_id: str = PRIMARY_REGION_ID
) -> LiveObservation:
    """Return the current observation for a region, refetching when stale.

    Providers are tried in order. If they all fail the last good observation is
    reused; if there is none, the synthetic provider fills in. Anything that is
    not a fresh live fetch is flagged degraded so the UI can say so rather than
    silently presenting stale or invented numbers as live.
    """
    get_region(region_id)  # validates the id
    ttl = cadence_for(region_id)

    with _lock:
        cached = _cached.get(region_id)
        if not force_refresh and cached is not None and cached.age_seconds() < ttl:
            return cached

    failures: list[str] = []
    for provider in build_providers(region_id=region_id):
        try:
            observation = provider.fetch()
        except Exception as exc:  # noqa: BLE001 — any upstream failure tries the next source
            log.warning("live fetch from %s failed: %s", provider.name, exc)
            failures.append(f"{provider.name}: {exc}")
            continue

        if failures:
            observation.notes.append(f"after {len(failures)} source(s) failed")
        with _lock:
            _cached[region_id] = observation
        _record(observation)
        return observation

    reason = "; ".join(failures) or "no provider available"
    if cached is not None:
        cached.degraded = True
        note = f"serving cached data — every live source failed ({reason})"
        if note not in cached.notes:
            cached.notes.append(note)
        return cached

    observation = SyntheticProvider(region_id=region_id).fetch(
        reason=f"every live source failed — {reason}"
    )
    with _lock:
        _cached[region_id] = observation
    _record(observation)
    return observation


def clear_cache(region_id: str | None = None) -> None:
    """Drop the cached observation for one region, or for all of them."""
    with _lock:
        if region_id is None:
            _cached.clear()
        else:
            _cached.pop(region_id, None)


# --------------------------------------------------------------------------
# Cadence ticker
# --------------------------------------------------------------------------

_ticker: threading.Thread | None = None
_stop = threading.Event()


def _tick_once() -> None:
    for region_id in region_ids():
        try:
            get_observation(region_id=region_id)
        except Exception as exc:  # noqa: BLE001 — one bad region must not stop the rest
            log.warning("scheduled refresh for %s failed: %s", region_id, exc)


def start_feed_clock() -> None:
    """Keep every region's observation arriving on its own cadence.

    `get_observation` would refresh lazily on the next request anyway, but a
    dashboard that is merely open — not being clicked — would then see nothing
    arrive. The ticker makes the feed a stream rather than a side effect of
    someone asking, which is what the live-feed view is showing.
    """
    global _ticker
    if _ticker is not None and _ticker.is_alive():
        return

    def run() -> None:
        # Wake several times per cadence so an observation lands close to when
        # it is due; polling *at* the cadence would round every arrival up to
        # the next tick. Clamped so a long cadence still does not busy-wait.
        shortest = min(cadence_for(r) for r in region_ids())
        interval = min(30.0, max(2.0, shortest / 4.0))
        while not _stop.wait(interval):
            _tick_once()

    _stop.clear()
    _ticker = threading.Thread(target=run, name="feed-clock", daemon=True)
    _ticker.start()
    log.info(
        "feed clock started: live cadence %ss, simulated cadence %ss",
        SETTINGS.cache_ttl,
        simulated_cadence(),
    )


def stop_feed_clock() -> None:
    _stop.set()


def storm_phase(region_id: str) -> dict | None:
    """Where the scripted storm currently is, for a simulated region."""
    if not get_region(region_id).simulated:
        return None
    now = datetime.now(timezone.utc)
    phase = phase_at(now)
    return {"phase": round(phase, 4), "label": phase_label(phase)}


__all__ = [
    "FeedArrival",
    "LiveObservation",
    "MetNoProvider",
    "OpenMeteoProvider",
    "SimulatedStormProvider",
    "SyntheticProvider",
    "build_providers",
    "cadence_for",
    "clear_cache",
    "clear_feed_log",
    "feed_log",
    "get_observation",
    "simulated_cadence",
    "start_feed_clock",
    "stop_feed_clock",
    "storm_phase",
]
