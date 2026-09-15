"""The NumPy forward pass must reproduce the PyTorch network."""

import numpy as np
import pytest

from rainshield.config import N_CHANNELS, REGION, SETTINGS
from rainshield.models.numpy_backend import forward, load_params

pytestmark = pytest.mark.skipif(
    not SETTINGS.weights_path.exists(), reason="checkpoint not present"
)


def _sample_tensor(seed: int = 0) -> np.ndarray:
    """A tensor spanning the physical ranges the channels really take."""
    rng = np.random.default_rng(seed)
    scales = [300.0, 12.0, 90.0, 60_000.0, 110.0, 1.0, 5.0, 2.5, 280.0, 45.0]
    return np.stack(
        [rng.random(REGION.shape).astype(np.float32) * s for s in scales]
    ).astype(np.float32)


def test_output_shape_and_range():
    params = load_params(SETTINGS.weights_path)
    out = forward(_sample_tensor(), params)
    assert out.shape == REGION.shape
    assert out.dtype == np.float32
    assert np.all((out >= 0.0) & (out <= 1.0))


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_matches_torch(seed):
    torch = pytest.importorskip("torch")
    from rainshield.models.network import RainShieldNet

    model = RainShieldNet()
    model.load_state_dict(torch.load(SETTINGS.weights_path, map_location="cpu"), strict=True)
    model.eval()

    tensor = _sample_tensor(seed)
    with torch.no_grad():
        expected = model(torch.from_numpy(tensor).unsqueeze(0)).squeeze().numpy()

    got = forward(tensor, load_params(SETTINGS.weights_path))
    np.testing.assert_allclose(got, expected, atol=1e-4, rtol=0)


def test_rejects_wrong_channel_count():
    params = load_params(SETTINGS.weights_path)
    with pytest.raises(ValueError):
        forward(np.zeros((N_CHANNELS + 3, *REGION.shape), dtype=np.float32), params)


# --------------------------------------------------------------------------
# Blocked attention
# --------------------------------------------------------------------------


def test_chunked_attention_is_bit_identical_to_one_block():
    """Blocking the query rows must not change a single bit of the output.

    Attention over the 45 x 39 grid is a 1755-token sequence, so a full score
    matrix is 1755 x 1755 — and it used to be materialised in full, three
    layers deep, which peaked at ~104 MB per forward pass and got the worker
    OOM-killed on a 512 MB instance. Softmax is independent per row, so the
    scores are now built a block of queries at a time.

    The guarantee that makes that safe is exactness, not closeness: a chunk
    size at or above the sequence length reproduces the original single-block
    computation, and every smaller size must agree with it bitwise.
    """
    import rainshield.models.numpy_backend as backend

    params = load_params(SETTINGS.weights_path)
    tensor = _sample_tensor(7)
    original = backend.ATTENTION_CHUNK
    try:
        backend.ATTENTION_CHUNK = REGION.cell_count   # one block: the old path
        reference = backend.forward(tensor, params)
        for chunk in (1, 17, 256, 1024, REGION.cell_count - 1):
            backend.ATTENTION_CHUNK = chunk
            assert np.array_equal(backend.forward(tensor, params), reference), (
                f"chunk size {chunk} changed the output"
            )
    finally:
        backend.ATTENTION_CHUNK = original


def test_attention_chunking_bounds_peak_memory():
    """The whole point: peak allocation must not scale with seq squared."""
    import tracemalloc

    import rainshield.models.numpy_backend as backend

    params = load_params(SETTINGS.weights_path)
    tensor = _sample_tensor(3)

    def peak_bytes(chunk: int) -> int:
        original = backend.ATTENTION_CHUNK
        backend.ATTENTION_CHUNK = chunk
        try:
            tracemalloc.start()
            backend.forward(tensor, params)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
            backend.ATTENTION_CHUNK = original
        return peak

    blocked = peak_bytes(256)
    whole = peak_bytes(REGION.cell_count)
    assert blocked < whole / 4, (
        f"blocked attention peaked at {blocked/1e6:.1f} MB against "
        f"{whole/1e6:.1f} MB unblocked — the saving has regressed"
    )
    # A forward pass must stay well clear of a 512 MB instance.
    assert blocked < 60e6
