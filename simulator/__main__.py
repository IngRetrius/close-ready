"""Command line of the simulator.

    uv run python -m simulator backfill [--until YYYY-MM-DD] [--out DIR]
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from simulator.backfill import simulate, write_ground_truth
from simulator.config import load_config
from simulator.report import report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m simulator", description="Close-Ready business simulator.")
    commands = parser.add_subparsers(dest="command", required=True)
    backfill = commands.add_parser("backfill", help="simulate the history before the cutover date")
    backfill.add_argument("--until", type=date.fromisoformat, help="last day to simulate (default: the day before cutover_date)")
    backfill.add_argument("--out", type=Path, default=Path("data"), help="output directory (default: data)")
    args = parser.parse_args(argv)

    config = load_config()
    until = args.until or config.run.cutover_date - timedelta(days=1)
    if not config.run.start_date <= until < config.run.cutover_date:
        parser.error(f"--until must be between {config.run.start_date} and the day before {config.run.cutover_date}")

    engine = simulate(config, until)
    path = write_ground_truth(engine, args.out)
    print(report(engine, until))
    print(f"\nGround truth written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
