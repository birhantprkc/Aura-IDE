"""Command shim for the bundled Web Research Drone."""

from __future__ import annotations

import sys
from pathlib import Path

_DRONE_DIR = Path(__file__).resolve().parent
if str(_DRONE_DIR) not in sys.path:
    sys.path.insert(0, str(_DRONE_DIR))

from research_pipeline import *  # noqa: F403 - compatibility re-exports for tests
from research_pipeline import main as _run_pipeline


def main() -> None:
    _run_pipeline()


if __name__ == "__main__":
    main()
