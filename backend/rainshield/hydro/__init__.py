"""Physics-based hydrology: tides, drainage catchments, pumping and routing.

Two stages, both mass-conserving and both independent of the neural network's
opinion about depth:

* **Stage A** (`balance`) is a lumped mass balance per drainage catchment.
  Rainfall minus infiltration over a catchment area gives an inflow in m3/s;
  tide-gated gravity outfall plus installed pump capacity gives a supply. The
  difference is the deficit, expressed as additional pumps of a standard unit
  size. No PDE, no state — one arithmetic pass per catchment per lead time.

* **Stage B** (`solver`) routes water between cells with a finite-volume
  diffusive-wave scheme, so rain landing on a slope arrives in the basin below
  instead of vanishing where it fell.

The trained network is not replaced by either. It supplies the dimensionless
susceptibility field that sets two sub-grid parameters the solver cannot
measure at 1 km — depression storage and drainage deficiency — which is the
role it can honestly fill. See `solver.parameter_field`.

Every parameter here (Manning's n, infiltration rates, pump capacities, tidal
constants, outfall invert levels) is an uncalibrated estimate. The output is
*defensible* — it conserves mass and responds to tide and pumping the way the
real system does — but it is not *validated* against observed inundation.
"""

from rainshield.hydro.balance import (
    CatchmentBalance,
    DrainageAssessment,
    assess_drainage,
)
from rainshield.hydro.stations import PumpStation, stations_for
from rainshield.hydro.terrain import DrainageTerrain, drainage_terrain
from rainshield.hydro.tide import TideState, tide_level

__all__ = [
    "CatchmentBalance",
    "DrainageAssessment",
    "DrainageTerrain",
    "PumpStation",
    "TideState",
    "assess_drainage",
    "drainage_terrain",
    "stations_for",
    "tide_level",
]
