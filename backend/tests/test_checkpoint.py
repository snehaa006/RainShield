"""The torch-free checkpoint reader must match torch.load exactly."""

import numpy as np
import pytest

from rainshield.config import SETTINGS
from rainshield.models.checkpoint import read_state_dict

pytestmark = pytest.mark.skipif(
    not SETTINGS.weights_path.exists(), reason="checkpoint not present"
)


def test_reads_every_tensor():
    state = read_state_dict(SETTINGS.weights_path)
    assert len(state) == 58
    assert state["conv1.0.weight"].shape == (32, 10, 3, 3)
    assert state["output_head.2.bias"].shape == (1,)


def test_bit_identical_to_torch():
    torch = pytest.importorskip("torch")
    mine = read_state_dict(SETTINGS.weights_path)
    reference = torch.load(SETTINGS.weights_path, map_location="cpu")

    assert set(mine) == set(reference)
    for key, tensor in reference.items():
        expected = tensor.detach().numpy()
        assert mine[key].shape == expected.shape, key
        np.testing.assert_array_equal(mine[key], expected, err_msg=key)
