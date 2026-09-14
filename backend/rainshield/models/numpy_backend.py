"""Pure-NumPy forward pass for RainShieldNet.

The network is small (175k parameters, a 726 KB checkpoint) and inference runs
on a single 45 x 39 grid, so PyTorch earns nothing at serving time while costing
a ~2.5 GB dependency and a slow cold start. This module runs the identical
weights and arithmetic with NumPy alone, which is what lets the backend deploy
on a small Render instance.

Equivalence with torch is asserted by backend/tests/test_numpy_backend.py.
"""

from __future__ import annotations

import numpy as np

EPS_BN = 1e-5
EPS_LN = 1e-5


def _conv2d(x: np.ndarray, weight: np.ndarray, bias: np.ndarray, padding: int) -> np.ndarray:
    """(C_in, H, W) -> (C_out, H, W) convolution, accumulated over kernel taps.

    Summing 9 shifted GEMMs is cheaper than materialising an im2col matrix at
    this grid size.
    """
    c_out, _, kh, kw = weight.shape
    _, h, w = x.shape
    if padding:
        x = np.pad(x, ((0, 0), (padding, padding), (padding, padding)))

    out = np.zeros((c_out, h, w), dtype=np.float64)
    for i in range(kh):
        for j in range(kw):
            # (C_out, C_in) @ (C_in, H*W) for this kernel tap
            patch = x[:, i : i + h, j : j + w].reshape(x.shape[0], -1)
            out += (weight[:, :, i, j] @ patch).reshape(c_out, h, w)
    return out + bias[:, None, None]


def _batch_norm(x: np.ndarray, p: dict, prefix: str) -> np.ndarray:
    mean = p[f"{prefix}.running_mean"][:, None, None]
    var = p[f"{prefix}.running_var"][:, None, None]
    weight = p[f"{prefix}.weight"][:, None, None]
    bias = p[f"{prefix}.bias"][:, None, None]
    return (x - mean) / np.sqrt(var + EPS_BN) * weight + bias


def _layer_norm(x: np.ndarray, weight: np.ndarray, bias: np.ndarray) -> np.ndarray:
    mean = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1, keepdims=True)
    return (x - mean) / np.sqrt(var + EPS_LN) * weight + bias


def _softmax(x: np.ndarray) -> np.ndarray:
    shifted = x - x.max(axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=-1, keepdims=True)


def _self_attention(x: np.ndarray, p: dict, prefix: str, nhead: int) -> np.ndarray:
    """Multi-head self-attention over a (seq, d_model) sequence."""
    seq, d_model = x.shape
    head_dim = d_model // nhead

    in_w = p[f"{prefix}.self_attn.in_proj_weight"]   # (3*d, d)
    in_b = p[f"{prefix}.self_attn.in_proj_bias"]     # (3*d,)
    qkv = x @ in_w.T + in_b
    q, k, v = np.split(qkv, 3, axis=-1)

    q = q.reshape(seq, nhead, head_dim)
    k = k.reshape(seq, nhead, head_dim)
    v = v.reshape(seq, nhead, head_dim)

    # One 2-D GEMM per head: numpy dispatches these to BLAS, whereas a single
    # batched 3-D matmul falls back to a much slower generic loop.
    context = np.empty((seq, nhead, head_dim), dtype=x.dtype)
    scale = 1.0 / np.sqrt(head_dim)
    for h in range(nhead):
        scores = (q[:, h] @ k[:, h].T) * scale          # (seq, seq)
        context[:, h] = _softmax(scores) @ v[:, h]
    context = context.reshape(seq, d_model)

    return context @ p[f"{prefix}.self_attn.out_proj.weight"].T + p[
        f"{prefix}.self_attn.out_proj.bias"
    ]


def _encoder_layer(x: np.ndarray, p: dict, prefix: str, nhead: int) -> np.ndarray:
    """One TransformerEncoderLayer with norm_first=False and ReLU activation.

    Matches torch's post-norm ordering:
        x = norm1(x + attn(x));  x = norm2(x + ff(x))
    Dropout is identity in eval mode, so it is omitted.
    """
    attn = _self_attention(x, p, prefix, nhead)
    x = _layer_norm(x + attn, p[f"{prefix}.norm1.weight"], p[f"{prefix}.norm1.bias"])

    hidden = np.maximum(x @ p[f"{prefix}.linear1.weight"].T + p[f"{prefix}.linear1.bias"], 0.0)
    ff = hidden @ p[f"{prefix}.linear2.weight"].T + p[f"{prefix}.linear2.bias"]

    return _layer_norm(x + ff, p[f"{prefix}.norm2.weight"], p[f"{prefix}.norm2.bias"])


def forward(tensor: np.ndarray, params: dict[str, np.ndarray], nhead: int = 4) -> np.ndarray:
    """Run RainShieldNet on a (C, H, W) raw-unit tensor; returns (H, W) in 0-1."""
    x = np.asarray(tensor, dtype=np.float64)

    x = _conv2d(x, params["conv1.0.weight"], params["conv1.0.bias"], padding=1)
    x = np.maximum(_batch_norm(x, params, "conv1.1"), 0.0)

    x = _conv2d(x, params["conv2.0.weight"], params["conv2.0.bias"], padding=1)
    x = np.maximum(_batch_norm(x, params, "conv2.1"), 0.0)

    # Squeeze-and-excitation over globally average-pooled channel context.
    pooled = x.mean(axis=(1, 2))                                        # (64,)
    hidden = np.maximum(params["se.1.weight"][:, :, 0, 0] @ pooled + params["se.1.bias"], 0.0)
    gate = params["se.3.weight"][:, :, 0, 0] @ hidden + params["se.3.bias"]
    x = x * (1.0 / (1.0 + np.exp(-gate)))[:, None, None]

    channels, height, width = x.shape
    seq = x.transpose(1, 2, 0).reshape(height * width, channels)
    for layer in range(3):
        seq = _encoder_layer(seq, params, f"transformer_encoder.layers.{layer}", nhead)
    x = seq.reshape(height, width, channels).transpose(2, 0, 1)

    hidden = np.maximum(
        (params["output_head.0.weight"][:, :, 0, 0] @ x.reshape(channels, -1))
        + params["output_head.0.bias"][:, None],
        0.0,
    )
    logits = (
        params["output_head.2.weight"][:, :, 0, 0] @ hidden
    ) + params["output_head.2.bias"][:, None]

    return (1.0 / (1.0 + np.exp(-logits))).reshape(height, width).astype(np.float32)


def load_params(path) -> dict[str, np.ndarray]:
    """Read a torch checkpoint into plain NumPy arrays.

    Uses torch when it is installed; otherwise falls back to the pickle-based
    reader in `checkpoint.py`, so no torch is needed at serving time.
    """
    try:
        import torch

        state = torch.load(path, map_location="cpu")
        return {k: v.detach().cpu().numpy().astype(np.float64) for k, v in state.items()}
    except ImportError:
        from rainshield.models.checkpoint import read_state_dict

        return {k: v.astype(np.float64) for k, v in read_state_dict(path).items()}
