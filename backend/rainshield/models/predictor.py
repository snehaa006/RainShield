"""Loads the trained network and turns live observations into susceptibility.

What the model actually learned
-------------------------------
The Stage 0 training target (nrsc_flood_ground_truth_1km.tif) is a pure
topographic mask — elevation <= 12 m AND slope <= 1.5 deg — both of which are
input channels 0 and 1. The network therefore learned a *terrain flood
susceptibility* map, and its output barely moves with the weather channels:
scaling every rainfall channel by 4x shifts the mean output by about +0.02.

So the model output is treated as susceptibility, and the live rainfall drives
the hazard on top of it (see rainshield.hazard). That keeps the trained network
doing what it is genuinely good at while letting the dashboard respond to real
weather.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

from rainshield.config import CHANNELS, N_CHANNELS, REGION, SETTINGS
from rainshield.grid import static_layers
from rainshield.ingest.base import (
    LiveObservation,
    brightness_temp_from_cloud,
    marshall_palmer_dbz,
)

log = logging.getLogger(__name__)

_lock = threading.Lock()
_model: dict | None = None
_load_error: str | None = None

#: A few parameters that must be present for the checkpoint to be usable, so a
#: truncated or mismatched file fails loudly at load rather than at inference.
REQUIRED_PARAMS = (
    "conv1.0.weight",
    "conv1.1.running_mean",
    "conv2.0.weight",
    "se.1.weight",
    "se.3.weight",
    "transformer_encoder.layers.0.self_attn.in_proj_weight",
    "transformer_encoder.layers.2.norm2.bias",
    "output_head.0.weight",
    "output_head.2.bias",
)


def build_input_tensor(observation: LiveObservation, lead: int) -> np.ndarray:
    """Assemble the (10, rows, cols) raw-unit model input for one lead time.

    Dynamic channels are derived from live data with the same formulas Stage 0
    used, so the values carry the units the network was trained on.
    """
    static = static_layers()
    rain_rate = observation.rain_rate[lead]
    rain_3h = observation.rain_3h[lead]

    # Catchment wetness as a 0-1 overflow index: soil saturation plus the
    # antecedent 24 hr load, the quantity the CWC gauge layer stood in for.
    river_level = np.clip(
        observation.soil_moisture * 0.6 + observation.antecedent_24h / 120.0, 0.0, 1.5
    )

    channels = {
        "elevation": static["elevation"],
        "slope": static["slope"],
        "infrastructure": static["infrastructure"],
        "population": static["population"],
        "aws_rain": rain_3h,
        "river_level": river_level,
        "gpm_rain": rain_rate,
        "gfs_forecast": rain_3h,
        "cloud_top_temp": brightness_temp_from_cloud(observation.cloud_cover),
        "radar_reflectivity": marshall_palmer_dbz(rain_rate),
    }

    tensor = np.stack([channels[name] for name in CHANNELS]).astype(np.float32)
    if tensor.shape != (N_CHANNELS, *REGION.shape):
        raise ValueError(f"input tensor has shape {tensor.shape}")
    return tensor


def _load_weights():
    """Load the checkpoint once; None means fall back to the analytical model.

    Weights are read into plain NumPy arrays and run through
    `rainshield.models.numpy_backend`, so serving needs no torch. The numpy
    path is verified against torch to ~1e-6 in the test suite.
    """
    global _load_error
    if SETTINGS.force_analytical:
        _load_error = "RAINSHIELD_FORCE_ANALYTICAL is set"
        return None
    if not SETTINGS.weights_path.exists():
        _load_error = f"weights not found at {SETTINGS.weights_path}"
        log.warning(_load_error)
        return None
    try:
        from rainshield.models.numpy_backend import load_params

        params = load_params(SETTINGS.weights_path)
        missing = [k for k in REQUIRED_PARAMS if k not in params]
        if missing:
            raise ValueError(f"checkpoint is missing {len(missing)} tensors, e.g. {missing[:3]}")
        _load_error = None
        log.info("loaded RainShieldNet weights from %s", SETTINGS.weights_path)
        return params
    except Exception as exc:  # noqa: BLE001 — serving must survive a bad checkpoint
        _load_error = f"{type(exc).__name__}: {exc}"
        log.error("failed to load weights: %s", _load_error)
        return None


def get_model():
    """The loaded parameter dict, or None when the analytical model is in use."""
    global _model
    with _lock:
        if _model is None and _load_error is None:
            _model = _load_weights()
        return _model


def model_status() -> dict:
    """What the /health endpoint reports about the inference backend."""
    model = get_model()
    return {
        "loaded": model is not None,
        "backend": "cnn-transformer" if model is not None else "analytical",
        "runtime": "numpy",
        "weights_path": str(SETTINGS.weights_path),
        "weights_present": SETTINGS.weights_path.exists(),
        "error": _load_error,
    }


def analytical_susceptibility() -> np.ndarray:
    """Terrain susceptibility without torch.

    A smooth logistic stand-in for the trained network, built from the same two
    terrain drivers the training target was derived from. Used when the
    checkpoint cannot be loaded, so the service still returns a sensible map.
    """
    static = static_layers()
    elevation, slope = static["elevation"], static["slope"]
    score = 2.2 - 0.32 * (elevation - 12.0) - 1.1 * (slope - 1.5)
    return (1.0 / (1.0 + np.exp(-np.clip(score, -30, 30)))).astype(np.float32)


def predict_susceptibility(observation: LiveObservation, lead: int = 0) -> np.ndarray:
    """Per-cell flood susceptibility, (rows, cols) in 0-1."""
    params = get_model()
    if params is None:
        return analytical_susceptibility()

    from rainshield.models.numpy_backend import forward

    return forward(build_input_tensor(observation, lead), params)
