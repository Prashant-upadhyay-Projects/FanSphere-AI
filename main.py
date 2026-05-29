"""FanSphere AI — CLI entrypoint.

Examples
--------
    # Full pipeline
    python main.py

    # Skip live API calls (useful in CI / offline runs)
    python main.py --skip-reddit --skip-statsbomb

    # Dry run — compute everything but don't write to Postgres
    python main.py --no-persist
"""

from __future__ import annotations

import argparse
import json
import sys

from src.config import get_logger
from src.main_pipeline import run

LOG = get_logger("fansphere.cli")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FanSphere AI pipeline runner")
    parser.add_argument("--skip-reddit",    action="store_true", help="Skip Reddit scraping")
    parser.add_argument("--skip-statsbomb", action="store_true", help="Skip StatsBomb fetch")
    parser.add_argument("--no-persist",     action="store_true", help="Do not write to Postgres")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        summary = run(
            skip_reddit=args.skip_reddit,
            skip_statsbomb=args.skip_statsbomb,
            persist=not args.no_persist,
        )
    except Exception as exc:  # noqa: BLE001 — top-level guard
        LOG.exception("Pipeline failed: %s", exc)
        return 1

    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
