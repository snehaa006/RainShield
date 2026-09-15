"""The pumping stations that drain the grid, and what they can lift.

Mumbai's stormwater system is gravity-fed to the sea through outfalls fitted
with flap gates. Where the outfall invert sits below high water the gate shuts
on a rising tide and the catchment behind it has no gravity discharge at all
until the tide falls again. BRIMSTOWAD — the Brihanmumbai Storm Water Drainage
project, recommended after the 2005 floods — answered that by building pumping
stations at the worst-affected outfalls, so those catchments can keep
discharging against a closed gate.

Seven stations are modelled, at their real locations. They are the ones
commonly named in BMC reporting on the programme.

    CAPACITIES ARE ESTIMATES. BMC has not published a machine-readable
    schedule of installed capacity, and the figures below are assembled from
    press and civic reporting of pump counts at a nominal ~6 m3/s per unit.
    They are order-correct, not authoritative. Every station therefore carries
    `capacity_basis`, and the API surfaces it, so no number here can be read
    off the dashboard as a verified fact. Outfall invert levels are a weaker
    estimate still: they are not published per outfall at all, and the values
    below are inferred from the requirement that these outfalls tide-lock
    around high water, which is the condition that motivated the pumps.

A simulated region gets generated stations, labelled as such. Theirs are given
a 25 mm/hr standard rather than 50 — an un-upgraded network — so that the
deficit path is actually exercised by the storm that region runs.

One structural consequence is worth stating plainly, because it bounds what
this model can conclude. Service areas are *derived from* capacity, so every
station is by construction sized correctly for its own design standard, give
or take rounding to whole cells. This model therefore cannot discover that a
station is under-built relative to what it was designed for — no such finding
would be real. What it can say is whether the rain exceeds the design standard,
and how much of the margin the tide takes away. Those are the two questions
that matter operationally, and both are answered honestly.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from rainshield.regions import PRIMARY_REGION_ID, get_region

#: Nominal capacity of one pump unit, m3/s. Deficits are reported as a count
#: of these so "what more is required" has a procurable answer rather than an
#: abstract volume.
PUMP_UNIT_CUMECS = 6.0

#: Default rainfall intensity the drainage network is designed to clear,
#: mm/hr; a station may override it.
#: BRIMSTOWAD's central recommendation was to rebuild Mumbai's drains to a
#: 50 mm/hr standard, up from the ~25 mm/hr colonial-era network that failed in
#: 2005. It is used here to *size* each station's service area: a station's
#: installed capacity divided by this intensity gives the area it was built to
#: drain. That is a stated assumption, not a survey — see `terrain`.
DESIGN_INTENSITY_MM_HR = 50.0


@dataclass(frozen=True)
class PumpStation:
    """One pumping station and the outfall it discharges through."""

    id: str
    name: str
    lon: float
    lat: float
    #: Number of installed pump units.
    pumps: int
    #: Installed capacity, m3/s. ESTIMATE — see `capacity_basis`.
    capacity_cumecs: float
    #: Outfall invert level, m above chart datum. The gravity gate shuts once
    #: sea level rises above this. ESTIMATE.
    outfall_invert_m_cd: float
    #: Gravity discharge capacity while the gate is open, m3/s. ESTIMATE.
    gravity_cumecs: float
    #: Year the station was commissioned, where reported.
    commissioned: int | None
    capacity_basis: str
    #: The rainfall intensity this station's network was built to clear,
    #: mm/hr. Sets the service area: capacity / intensity is the area it
    #: drains. A lower standard means the same pumps cover more ground and
    #: therefore fail sooner, which is what an un-upgraded network looks like.
    design_intensity_mm_hr: float = DESIGN_INTENSITY_MM_HR
    #: True when the station is invented along with its region.
    generated: bool = False

    @property
    def unit_cumecs(self) -> float:
        return self.capacity_cumecs / self.pumps if self.pumps else PUMP_UNIT_CUMECS


_BMC_BASIS = (
    "ESTIMATE — pump count from public BMC/press reporting at a nominal "
    "6 m3/s per unit; not an audited figure."
)
_GENERATED_BASIS = "GENERATED — invented along with the simulated region."


#: The BRIMSTOWAD stations, in commissioning order. All seven fall inside the
#: 72.75-73.10 E, 18.85-19.25 N analysis grid; the first four are in the
#: island city and the last three in the western suburbs.
BRIMSTOWAD_STATIONS: tuple[PumpStation, ...] = (
    PumpStation(
        id="haji-ali", name="Haji Ali", lon=72.8095, lat=18.9776,
        pumps=6, capacity_cumecs=36.0, outfall_invert_m_cd=1.8,
        gravity_cumecs=30.0, commissioned=2008, capacity_basis=_BMC_BASIS,
    ),
    PumpStation(
        id="love-grove", name="Love Grove (Worli)", lon=72.8175, lat=18.9963,
        pumps=6, capacity_cumecs=36.0, outfall_invert_m_cd=1.7,
        gravity_cumecs=30.0, commissioned=2009, capacity_basis=_BMC_BASIS,
    ),
    PumpStation(
        id="cleveland", name="Cleveland Bunder", lon=72.8134, lat=18.9903,
        pumps=3, capacity_cumecs=18.0, outfall_invert_m_cd=1.6,
        gravity_cumecs=16.0, commissioned=2010, capacity_basis=_BMC_BASIS,
    ),
    PumpStation(
        id="britannia", name="Britannia (Reay Road)", lon=72.8447, lat=18.9846,
        pumps=3, capacity_cumecs=18.0, outfall_invert_m_cd=1.5,
        gravity_cumecs=14.0, commissioned=2011, capacity_basis=_BMC_BASIS,
    ),
    PumpStation(
        id="gazdhar-bandh", name="Gazdhar Bandh (Santacruz)", lon=72.8291, lat=19.0912,
        pumps=3, capacity_cumecs=18.0, outfall_invert_m_cd=1.7,
        gravity_cumecs=15.0, commissioned=2015, capacity_basis=_BMC_BASIS,
    ),
    PumpStation(
        id="irla", name="Irla (Juhu)", lon=72.8286, lat=19.1073,
        pumps=3, capacity_cumecs=18.0, outfall_invert_m_cd=1.6,
        gravity_cumecs=15.0, commissioned=2016, capacity_basis=_BMC_BASIS,
    ),
    PumpStation(
        id="mogra", name="Mogra (Andheri)", lon=72.8540, lat=19.1290,
        pumps=6, capacity_cumecs=36.0, outfall_invert_m_cd=1.9,
        gravity_cumecs=20.0, commissioned=2024, capacity_basis=_BMC_BASIS,
    ),
)


#: Stations for the simulated delta. Deliberately under-provisioned relative to
#: the storm that region runs, so the deficit path is exercised every cycle.
SIMULATED_STATIONS: tuple[PumpStation, ...] = (
    PumpStation(
        id="sim-harbour", name="Harbour Front Pumping Station", lon=80.330, lat=12.912,
        pumps=4, capacity_cumecs=24.0, outfall_invert_m_cd=1.0,
        gravity_cumecs=18.0, commissioned=2012, capacity_basis=_GENERATED_BASIS,
        design_intensity_mm_hr=25.0, generated=True,
    ),
    PumpStation(
        id="sim-estuary", name="Estuary Town Pumping Station", lon=80.324, lat=13.046,
        pumps=3, capacity_cumecs=18.0, outfall_invert_m_cd=0.9,
        gravity_cumecs=14.0, commissioned=2017, capacity_basis=_GENERATED_BASIS,
        design_intensity_mm_hr=25.0, generated=True,
    ),
    PumpStation(
        id="sim-northport", name="North Port Pumping Station", lon=80.332, lat=13.150,
        pumps=2, capacity_cumecs=12.0, outfall_invert_m_cd=1.1,
        gravity_cumecs=10.0, commissioned=2020, capacity_basis=_GENERATED_BASIS,
        design_intensity_mm_hr=25.0, generated=True,
    ),
)


@lru_cache(maxsize=8)
def stations_for(region_id: str = PRIMARY_REGION_ID) -> tuple[PumpStation, ...]:
    """Every pumping station inside a region's grid.

    Stations outside the region's bounds are dropped rather than clamped to
    the edge, so a region that simply has no modelled station reports an
    honest zero installed capacity instead of a station in the wrong place.
    """
    profile = get_region(region_id)
    catalogue = SIMULATED_STATIONS if profile.simulated else BRIMSTOWAD_STATIONS
    g = profile.geometry
    return tuple(
        s for s in catalogue
        if g.west <= s.lon <= g.east and g.south <= s.lat <= g.north
    )


def installed_capacity(region_id: str = PRIMARY_REGION_ID) -> float:
    """Total installed pump capacity across a region, m3/s."""
    return sum(s.capacity_cumecs for s in stations_for(region_id))
