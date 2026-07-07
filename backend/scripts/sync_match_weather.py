"""Sync match weather from Open-Meteo forecast."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wcpa.worldcup.environment import WorldCupEnvironmentService


def main() -> None:
    report = WorldCupEnvironmentService().sync_match_weather()
    print(report.__dict__)


if __name__ == "__main__":
    main()
