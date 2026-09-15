"""A harmonic tide model for the coastal boundary.

Mumbai floods when heavy rain coincides with a high tide. The city's storm
drains discharge to the sea through gravity outfalls fitted with flap gates;
once sea level rises above an outfall's invert the gate shuts, gravity
discharge stops, and everything the catchment produces has to be lifted by
pump or else stand in the streets. Both 26 July 2005 and 29 August 2017 were
extreme rainfall landing on a high tide. "Is the installed pumping capacity
sufficient?" therefore has no single answer — it flips between low and high
water, which is exactly what this module exists to let the dashboard show.

Four constituents are enough for that. The semidiurnal pair M2 (principal
lunar) and S2 (principal solar) beat against each other to produce the
spring-neap cycle at 14.77 days, and the diurnal pair K1 and O1 supply the
diurnal inequality that makes successive high waters unequal. A full
constituent set would add precision this model has no use for.

    eta(t) = MSL + sum_i A_i cos(2*pi*t/T_i - g_i)

Heights are metres above **chart datum**, the convention Indian tide tables
and outfall invert levels both use, so the gate test is a direct comparison.

    Uncalibrated. The amplitudes below are order-correct for their ports and
    give a plausible spring range, but the phases are referred to an arbitrary
    epoch rather than fitted to observations. Predicted high water will not
    line up with a real tide table. Treat the *shape* of the curve and the
    *fraction of time the gates are shut* as meaningful; do not treat a
    specific predicted water level at a specific minute as a forecast.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from rainshield.regions import PRIMARY_REGION_ID, get_region

#: Epoch the phases are referred to. Arbitrary but fixed, so that every host
#: and every request computes the same tide for the same instant.
TIDE_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Constituent:
    """One tidal harmonic: amplitude in m, period in hours, phase in degrees."""

    name: str
    amplitude: float
    period_hours: float
    phase_deg: float


#: Periods are physical constants; amplitudes and phases are the estimates.
M2_HOURS = 12.4206012
S2_HOURS = 12.0
K1_HOURS = 23.9344721
O1_HOURS = 25.8193417


@dataclass(frozen=True)
class TidalRegime:
    """The tidal character of one region's coast."""

    #: Mean sea level, m above chart datum.
    mean_sea_level_m: float
    constituents: tuple[Constituent, ...]
    #: Free-text provenance, surfaced in the API so the figures are not
    #: mistaken for a fitted harmonic analysis.
    basis: str

    @property
    def highest_astronomical_tide_m(self) -> float:
        """All constituents in phase — the practical upper bound."""
        return self.mean_sea_level_m + sum(c.amplitude for c in self.constituents)

    @property
    def lowest_astronomical_tide_m(self) -> float:
        return self.mean_sea_level_m - sum(c.amplitude for c in self.constituents)

    @property
    def spring_range_m(self) -> float:
        """M2 + S2 in phase, doubled: the classic spring range."""
        by_name = {c.name: c.amplitude for c in self.constituents}
        return 2.0 * (by_name.get("M2", 0.0) + by_name.get("S2", 0.0))


#: Mumbai (Apollo Bandar). A macrotidal port: MSL sits ~2.5 m above chart
#: datum and the spring range is ~4.5 m, which is why so much of the drainage
#: network is tide-locked for part of every day.
MUMBAI_TIDE = TidalRegime(
    mean_sea_level_m=2.51,
    constituents=(
        Constituent("M2", 1.68, M2_HOURS, 0.0),
        Constituent("S2", 0.62, S2_HOURS, 0.0),
        Constituent("K1", 0.28, K1_HOURS, 90.0),
        Constituent("O1", 0.12, O1_HOURS, 90.0),
    ),
    basis=(
        "Amplitudes are order-correct for Apollo Bandar (spring range ~4.6 m, "
        "HAT ~5.2 m above chart datum); phases are referred to an arbitrary "
        "epoch, not fitted to observations. ESTIMATE — not a tide table."
    ),
)

#: The simulated delta. Given a moderate tide rather than a microtidal one so
#: that the gating mechanism is exercised in the region built to exercise
#: things. Entirely invented, like the rest of that region.
COROMANDEL_TIDE = TidalRegime(
    mean_sea_level_m=1.40,
    constituents=(
        Constituent("M2", 1.05, M2_HOURS, 0.0),
        Constituent("S2", 0.38, S2_HOURS, 0.0),
        Constituent("K1", 0.22, K1_HOURS, 90.0),
        Constituent("O1", 0.10, O1_HOURS, 90.0),
    ),
    basis="GENERATED — a plausible mesotidal coast for the simulated region.",
)

_REGIMES: dict[str, TidalRegime] = {
    "mumbai": MUMBAI_TIDE,
    "coromandel": COROMANDEL_TIDE,
}


def regime_for(region_id: str = PRIMARY_REGION_ID) -> TidalRegime:
    """The tidal regime of a region, falling back to the primary one."""
    return _REGIMES.get(region_id, MUMBAI_TIDE)


@dataclass(frozen=True)
class TideState:
    """Sea level at one instant, and how it is moving."""

    #: Metres above chart datum.
    level_m: float
    #: Rate of change, m/hr. Positive on the flood, negative on the ebb.
    rate_m_per_hr: float
    #: Where this sits between LAT (0) and HAT (1).
    normalised: float
    #: "high", "low", "flooding" or "ebbing".
    phase: str
    valid_at: datetime
    regime: TidalRegime

    @property
    def is_rising(self) -> bool:
        return self.rate_m_per_hr > 0.0


def _elapsed_hours(moment: datetime) -> float:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (moment - TIDE_EPOCH).total_seconds() / 3600.0


def sea_level(moment: datetime, region_id: str = PRIMARY_REGION_ID) -> float:
    """Sea level in m above chart datum at `moment`."""
    regime = regime_for(region_id)
    hours = _elapsed_hours(moment)
    total = regime.mean_sea_level_m
    for c in regime.constituents:
        total += c.amplitude * np.cos(
            2.0 * np.pi * hours / c.period_hours - np.deg2rad(c.phase_deg)
        )
    return float(total)


def tide_level(
    moment: datetime | None = None,
    region_id: str = PRIMARY_REGION_ID,
    override_m: float | None = None,
) -> TideState:
    """Full tide state at `moment`, or now.

    `override_m` pins the level directly, for the dashboard's tide control and
    for "what would this storm do at high water?" questions. An overridden
    state reports zero rate and a phase read from the level alone, because a
    pinned level carries no information about which way the tide is going.
    """
    moment = moment or datetime.now(timezone.utc)
    regime = regime_for(region_id)
    span = regime.highest_astronomical_tide_m - regime.lowest_astronomical_tide_m

    if override_m is not None:
        level = float(override_m)
        normalised = (level - regime.lowest_astronomical_tide_m) / span if span else 0.5
        return TideState(
            level_m=level,
            rate_m_per_hr=0.0,
            normalised=float(np.clip(normalised, 0.0, 1.0)),
            phase="high" if normalised >= 0.5 else "low",
            valid_at=moment,
            regime=regime,
        )

    level = sea_level(moment, region_id)
    # Central difference over six minutes — the curve is smooth at that scale.
    step_hr = 0.1
    hours = _elapsed_hours(moment)
    ahead = regime.mean_sea_level_m
    behind = regime.mean_sea_level_m
    for c in regime.constituents:
        w = 2.0 * np.pi / c.period_hours
        g = np.deg2rad(c.phase_deg)
        ahead += c.amplitude * np.cos(w * (hours + step_hr) - g)
        behind += c.amplitude * np.cos(w * (hours - step_hr) - g)
    rate = float((ahead - behind) / (2.0 * step_hr))

    normalised = float(
        np.clip((level - regime.lowest_astronomical_tide_m) / span if span else 0.5, 0.0, 1.0)
    )
    if abs(rate) < 0.05:
        phase = "high" if normalised >= 0.5 else "low"
    else:
        phase = "flooding" if rate > 0 else "ebbing"

    return TideState(
        level_m=level,
        rate_m_per_hr=rate,
        normalised=normalised,
        phase=phase,
        valid_at=moment,
        regime=regime,
    )
