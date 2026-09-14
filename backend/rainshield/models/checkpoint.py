"""Read a PyTorch ``.pth`` state dict without importing torch.

A torch checkpoint is a zip archive holding a pickled object graph
(``data.pkl``) plus one flat binary blob per tensor storage under ``data/``.
The pickle only references a handful of torch symbols, so a restricted
``Unpickler`` that stubs those out is enough to recover every tensor as a NumPy
array — which keeps a ~2.5 GB dependency out of the serving image.

Only the subset torch actually emits for a plain ``state_dict`` is supported
(``_rebuild_tensor_v2`` over dense CPU storages). Anything else raises, rather
than silently returning wrong weights.
"""

from __future__ import annotations

import collections
import pickle
import zipfile

import numpy as np

#: torch storage class name -> NumPy dtype.
_STORAGE_DTYPES: dict[str, np.dtype] = {
    "DoubleStorage": np.dtype("float64"),
    "FloatStorage": np.dtype("float32"),
    "HalfStorage": np.dtype("float16"),
    "LongStorage": np.dtype("int64"),
    "IntStorage": np.dtype("int32"),
    "ShortStorage": np.dtype("int16"),
    "CharStorage": np.dtype("int8"),
    "ByteStorage": np.dtype("uint8"),
    "BoolStorage": np.dtype("bool"),
}


class _StorageType:
    """Stand-in for ``torch.FloatStorage`` and friends."""

    def __init__(self, name: str):
        self.name = name
        self.dtype = _STORAGE_DTYPES[name]


def _rebuild_tensor_v2(storage, storage_offset, size, stride, *_rest) -> np.ndarray:
    """Reconstruct a strided view over a flat storage, as torch would."""
    flat: np.ndarray = storage
    size = tuple(int(s) for s in size)
    stride = tuple(int(s) for s in stride)

    if not size:  # 0-d tensor, e.g. num_batches_tracked
        return np.array(flat[int(storage_offset)])

    itemsize = flat.dtype.itemsize
    return np.lib.stride_tricks.as_strided(
        flat[int(storage_offset) :],
        shape=size,
        strides=tuple(s * itemsize for s in stride),
    ).copy()


class _Unpickler(pickle.Unpickler):
    """Resolves torch symbols to local stand-ins and loads storages on demand."""

    def __init__(self, file, archive: zipfile.ZipFile, prefix: str):
        super().__init__(file, encoding="utf-8")
        self._archive = archive
        self._prefix = prefix

    def find_class(self, module: str, name: str):
        if module == "torch._utils" and name == "_rebuild_tensor_v2":
            return _rebuild_tensor_v2
        if module == "torch" and name in _STORAGE_DTYPES:
            return _StorageType(name)
        if module == "collections" and name == "OrderedDict":
            # The real class: pickle's reduce protocol for OrderedDict expects
            # its own __init__/__setitem__, so a plain dict will not do.
            return collections.OrderedDict
        raise pickle.UnpicklingError(
            f"unsupported symbol in checkpoint: {module}.{name}. "
            "Install torch to load this file."
        )

    def persistent_load(self, pid):
        # torch emits ("storage", storage_type, key, location, numel)
        if not (isinstance(pid, tuple) and pid and pid[0] == "storage"):
            raise pickle.UnpicklingError(f"unsupported persistent id: {pid!r}")
        _, storage_type, key, _location, numel = pid
        dtype = storage_type.dtype if isinstance(storage_type, _StorageType) else np.dtype(storage_type)
        raw = self._archive.read(f"{self._prefix}data/{key}")
        array = np.frombuffer(raw, dtype=dtype)
        if array.size != int(numel):
            raise ValueError(
                f"storage {key}: expected {numel} elements, blob holds {array.size}"
            )
        return array


def read_state_dict(path) -> dict[str, np.ndarray]:
    """Load a ``.pth`` state dict as ``{parameter name: numpy array}``."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        try:
            pickle_name = next(n for n in names if n.endswith("data.pkl"))
        except StopIteration as exc:
            raise ValueError(f"{path} is not a torch zip checkpoint") from exc

        prefix = pickle_name[: -len("data.pkl")]

        byteorder_entry = f"{prefix}byteorder"
        if byteorder_entry in names and archive.read(byteorder_entry) != b"little":
            raise ValueError("big-endian checkpoints are not supported")

        with archive.open(pickle_name) as handle:
            state = _Unpickler(handle, archive, prefix).load()

    if not isinstance(state, dict):
        raise ValueError(f"expected a state dict, got {type(state).__name__}")
    return {str(k): np.asarray(v) for k, v in state.items()}
