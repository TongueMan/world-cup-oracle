"""Build environment feature indexes from saved match weather snapshots."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wcpa.worldcup.environment import WorldCupEnvironmentService


def main() -> None:
    report = WorldCupEnvironmentService().build_match_environment_features()
    print(report.__dict__)


if __name__ == "__main__":
    main()
