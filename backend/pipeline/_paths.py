"""Repo-root-anchored data paths shared by every pipeline stage.

The stage scripts used to hard-code "./processed_data/...", which only worked
when they were run from the repository root. Resolving against this file's
own location lets them run from anywhere (and from the deployed backend).
"""

from __future__ import annotations

import os
from pathlib import Path

#: backend/pipeline/_paths.py -> backend/pipeline -> backend -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DIR = Path(os.getenv("RAINSHIELD_PROCESSED_DIR", REPO_ROOT / "processed_data"))
RAW_DIR = Path(os.getenv("RAINSHIELD_RAW_DIR", REPO_ROOT / "raw_data_feeds"))

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

__all__ = ["REPO_ROOT", "PROCESSED_DIR", "RAW_DIR"]
