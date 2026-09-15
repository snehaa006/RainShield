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
from typing import Callable
import time
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

#: One in-flight refresh per region, so concurrent callers share a single fetch.
#: Each entry is (gate, started_at) — the start time so a refresh that somehow
#: never finishes cannot wedge the region's feed shut forever.
_inflight_lock = threading.Lock()
_inflight: dict[str, tuple[threading.Event, float]] = {}

#: A refresh older than this is presumed lost and a new one is allowed. Every
#: upstream call is already bounded by RAINSHIELD_HTTP_TIMEOUT, so reaching this
#: means something unforeseen — and a frozen feed is worse than a duplicate call.
MAX_INFLIGHT_SECONDS = 300.0

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


#: Called with every observation that lands.
#:
#: The point of the hook is that scoring a new observation is expensive and has
#: no business being on a visitor's critical path. Subscribers run after the
#: observation is cached, so anything they precompute is already warm by the
#: time a request asks for it. Kept as a subscription rather than a direct call
#: so that `ingest` does not have to import the model layer.
#:
#: Subscribers are dispatched on their own thread, and that is not tidiness —
#: it is load-bearing. `_record` runs inside the provider chain, which runs
#: *before* the gate that releases every request waiting on that refresh. The
#: first version of this hook called subscribers inline, the only subscriber
#: scored the observation (~7.5 CPU-seconds), and the gate stayed shut for the
#: better part of a minute per region: the dashboard sat on "Loading live
#: forecast" until it timed out, and reloading only added contention. No
#: subscriber, however careful, is allowed to be able to do that again.
_subscribers: list[Callable[[LiveObservation], None]] = []


def on_observation(callback: Callable[[LiveObservation], None]) -> None:
    """Run `callback` whenever a new observation is cached."""
    if callback not in _subscribers:
        _subscribers.append(callback)


def clear_observation_subscribers() -> None:
    _subscribers.clear()


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

    callbacks = list(_subscribers)
    if callbacks:
        threading.Thread(
            target=_notify,
            args=(observation, callbacks),
            name=f"observation-subscribers-{observation.region_id}",
            daemon=True,
        ).start()


def _notify(observation: LiveObservation, callbacks: list) -> None:
    """Run subscribers off the feed's thread, one failure at a time."""
    for callback in callbacks:
        try:
            callback(observation)
        except Exception as exc:  # noqa: BLE001 — a subscriber must never lose the feed
            log.warning(
                "observation subscriber %s failed: %s: %s",
                getattr(callback, "__name__", callback),
                type(exc).__name__,
                exc,
            )


def feed_log(region_id: str = PRIMARY_REGION_ID) -> list[FeedArrival]:
    """Arrivals for a region, oldest first."""
    with _lock:
        return list(_feed_log.get(region_id, ()))


def clear_feed_log() -> None:
    with _lock:
        _feed_log.clear()


def clear_inflight() -> None:
    """Forget any in-flight refresh. For tests; the threads finish harmlessly."""
    with _inflight_lock:
        _inflight.clear()


# --------------------------------------------------------------------------
# Fetch + cache
# --------------------------------------------------------------------------


def _run_chain(region_id: str) -> LiveObservation:
    """Walk the provider chain once and return whatever it yields.

    Never raises: if every source fails it degrades to the last good
    observation, then to the synthetic field.
    """
    with _lock:
        cached = _cached.get(region_id)

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


def _start_fetch(region_id: str) -> threading.Event:
    """Ensure exactly one refresh is in flight for a region, and return its gate.

    Without this the fetch was a thundering herd: the dashboard asks for the
    forecast and the trend in parallel, the warm-up thread is running too, and
    the cache is empty, so three callers each walked the whole provider chain at
    once — tripling the load on an upstream that rate-limits per IP, which is
    the very thing that makes it slow.
    """
    now = time.monotonic()
    with _inflight_lock:
        existing = _inflight.get(region_id)
        if existing is not None and now - existing[1] < MAX_INFLIGHT_SECONDS:
            return existing[0]
        if existing is not None:
            log.warning(
                "refresh for %s has been running %.0fs — starting another",
                region_id,
                now - existing[1],
            )
        gate = threading.Event()
        _inflight[region_id] = (gate, now)

    def run() -> None:
        try:
            _run_chain(region_id)
        except Exception as exc:  # noqa: BLE001 — a refresh must never kill the thread
            log.error("refresh for %s failed unexpectedly: %s", region_id, exc)
        finally:
            with _inflight_lock:
                # Only clear the slot if it is still ours: a refresh presumed
                # lost may have been replaced, and it must not evict its successor.
                current = _inflight.get(region_id)
                if current is not None and current[0] is gate:
                    _inflight.pop(region_id, None)
            gate.set()

    threading.Thread(target=run, name=f"fetch-{region_id}", daemon=True).start()
    return gate


def get_observation(
    force_refresh: bool = False,
    region_id: str = PRIMARY_REGION_ID,
    budget: float | None = None,
) -> LiveObservation:
    """Return the current observation for a region, refreshing when stale.

    The refresh runs on a background thread and the caller waits at most
    `budget` seconds for it. Past that it is served the last good observation —
    flagged degraded and stale — rather than holding the request open. A slow
    upstream should make the board *older*, not make it never load.
    """
    get_region(region_id)  # validates the id
    ttl = cadence_for(region_id)

    with _lock:
        cached = _cached.get(region_id)
    if not force_refresh and cached is not None and cached.age_seconds() < ttl:
        return cached

    gate = _start_fetch(region_id)
    budget = SETTINGS.fetch_budget if budget is None else budget
    if gate.wait(max(0.0, budget)):
        with _lock:
            fresh = _cached.get(region_id)
        if fresh is not None:
            return fresh

    # The refresh is still running. Serve what we have; it will land shortly and
    # the next poll, or the feed clock, will pick it up.
    with _lock:
        cached = _cached.get(region_id)
    if cached is not None:
        cached.degraded = True
        note = f"upstream slow — served the previous observation after {budget:.0f}s"
        if note not in cached.notes:
            cached.notes.append(note)
        return cached

    # Nothing cached at all: first load against a slow upstream. A labelled
    # synthetic field now beats a spinner for however long the feed takes.
    observation = SyntheticProvider(region_id=region_id).fetch(
        reason=f"live feed still loading after {budget:.0f}s — retrying in the background"
    )
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
            # The clock is the one caller that should wait for the network: it
            # has nobody blocked behind it, and its whole job is to land the
            # observation the request path declines to wait for.
            get_observation(region_id=region_id, budget=120.0)
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
    "clear_inflight",
    "feed_log",
    "get_observation",
    "simulated_cadence",
    "start_feed_clock",
    "stop_feed_clock",
    "storm_phase",
]
