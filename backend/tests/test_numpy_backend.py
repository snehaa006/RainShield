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
