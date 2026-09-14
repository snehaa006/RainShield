"""Standalone live inference — fetch current weather, score the grid, print or save.

Runs the whole chain outside the API:

    python backend/pipeline/infer_realtime.py                    # summary table
    python backend/pipeline/infer_realtime.py --lead 180 --json out.json
    python backend/pipeline/infer_realtime.py --provider synthetic --geotiff risk.tif

No retraining and no rebuild of the Stage 0 rasters: the static layers come from
the Stage 1 tensor and only the weather channels are refetched.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Make the `rainshield` package importable when run as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description="RainShield live inference")
    parser.add_argument("--lead", type=int, default=0, help="lead time in minutes")
    parser.add_argument(
        "--provider",
        choices=("openmeteo", "synthetic"),
        help="override RAINSHIELD_PROVIDER",
    )
    parser.add_argument("--extra-rainfall", type=float, default=0.0, help="injected rainfall, mm")
    parser.add_argument("--soil-saturation", type=float, default=1.0)
    parser.add_argument("--drainage-capacity", type=float, default=1.0)
    parser.add_argument("--json", type=Path, help="write the full payload to this file")
    parser.add_argument("--geotiff", type=Path, help="write the risk grid as a GeoTIFF (needs rasterio)")
    parser.add_argument("--all-leads", action="store_true", help="summarise every lead time")
    args = parser.parse_args()

    if args.provider:
        os.environ["RAINSHIELD_PROVIDER"] = args.provider

    from rainshield.config import LEAD_TIMES
    from rainshield.hazard import WhatIf
    from rainshield.service import forecast_payload

    what_if = WhatIf(args.extra_rainfall, args.soil_saturation, args.drainage_capacity)
    leads = list(LEAD_TIMES) if args.all_leads else [args.lead]

    started = time.perf_counter()
    payloads = {lead: forecast_payload(lead, what_if) for lead in leads}
    elapsed = time.perf_counter() - started

    first = payloads[leads[0]]
    feed = first["observation"]
    model = first["model"]

    print(f"  feed    : {feed['source']}  fetched {feed['fetchedAt']}")
    if feed["degraded"]:
        print(f"  WARNING : degraded — {'; '.join(feed['notes'])}")
    print(f"  model   : {model['backend']} via {model['runtime']} (loaded={model['loaded']})")
    if model["error"]:
        print(f"  note    : {model['error']}")
    if what_if.is_active():
        print(
            f"  what-if : +{what_if.extra_rainfall} mm, soil x{what_if.soil_saturation}, "
            f"drainage x{what_if.drainage_capacity}"
        )
    print()
    header = f"  {'lead':>6} {'tier':>9} {'peakRisk':>9} {'peakP':>7} {'rain3h':>8} {'depth':>7} {'pop@risk':>10} {'cells':>6}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for lead in leads:
        s = payloads[lead]["summary"]
        print(
            f"  {lead:>6} {s['tier']:>9} {s['peakRisk']:>9.3f} {s['peakFloodProbability']:>7.3f} "
            f"{s['peakRainfall3h']:>8.1f} {s['peakDepth']:>7.2f} {s['populationAtRisk']:>10,} {s['floodedArea']:>6}"
        )

    top = payloads[leads[-1]]["wards"][:5]
    if top:
        print(f"\n  highest-risk wards at +{leads[-1]} min:")
        for ward in top:
            print(f"    {ward['tier']:>8}  {ward['risk']:.3f}  {ward['name']}")

    print(f"\n  inference completed in {elapsed:.2f}s")

    if args.json:
        payload = payloads[leads[0]] if len(leads) == 1 else {str(k): v for k, v in payloads.items()}
        args.json.write_text(json.dumps(payload, indent=2))
        print(f"  wrote {args.json}")

    if args.geotiff:
        _write_geotiff(args.geotiff, payloads[leads[0]]["cells"]["risk"])
        print(f"  wrote {args.geotiff}")

    return 0


def _write_geotiff(path: Path, risk_values: list[float]) -> None:
    """Save the risk grid, copying georeferencing from the master DEM."""
    import numpy as np
    import rasterio

    from rainshield.config import REGION, SETTINGS

    with rasterio.open(SETTINGS.processed_dir / "dem_1km_master.tif") as src:
        meta = src.meta.copy()
    meta.update({"dtype": "float32", "count": 1})
    grid = np.asarray(risk_values, dtype=np.float32).reshape(REGION.shape)
    with rasterio.open(path, "w", **meta) as dst:
        dst.write(grid, 1)


if __name__ == "__main__":
    raise SystemExit(main())
