"""Sync venue elevation from Open-Meteo."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wcpa.worldcup.environment import WorldCupEnvironmentService


def main() -> None:
    report = WorldCupEnvironmentService().sync_venue_elevation()
    print(report.__dict__)


if __name__ == "__main__":
    main()
