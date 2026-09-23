"""Command-line interface for gleis404."""

from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime
from pathlib import Path

from gleis404 import __version__
from gleis404.client import TransitousClient
from gleis404.collector import (
    CollectorConfig,
    CycleStats,
    collect_cycle,
    load_config,
    with_overrides,
)
from gleis404.storage import Database


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser for the gleis404 CLI."""
    parser = argparse.ArgumentParser(
        prog="gleis404",
        description=(
            "Collect realtime public transit departures and analyze "
            "punctuality trends."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")

    collect_parser = subparsers.add_parser(
        "collect",
        help="collect departures for the configured stations",
        description=(
            "Poll every configured station and store departures plus "
            "their realtime status in the SQLite database."
        ),
    )
    collect_parser.add_argument(
        "--once",
        action="store_true",
        help="run a single collection cycle and exit",
    )
    collect_parser.add_argument(
        "--interval",
        type=int,
        metavar="SECONDS",
        help="override the configured seconds between cycles",
    )
    collect_parser.add_argument(
        "--results",
        type=int,
        metavar="N",
        help="override the number of departures fetched per station",
    )
    collect_parser.add_argument(
        "--config",
        metavar="PATH",
        help="watchlist TOML to use instead of ./gleis404.toml or the built-in default",
    )
    collect_parser.add_argument(
        "--db",
        metavar="PATH",
        help="SQLite database path to use instead of the configured one",
    )
    collect_parser.set_defaults(func=_cmd_collect)
    return parser


def _format_cycle(stats: CycleStats, next_in: int | None) -> str:
    """Render one cycle's result as a log line."""
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    line = (
        f"[{stamp}] {stats.inserted} new, {stats.updated} refreshed"
        f" ({len(stats.failures)} errors)"
    )
    if stats.failures:
        line += " | " + "; ".join(stats.failures)
    if next_in is not None:
        line += f" | next cycle in {next_in}s"
    return line


def _open_resources(config: CollectorConfig) -> tuple[Database, TransitousClient]:
    """Open the database and API client for collection."""
    return Database(config.database), TransitousClient()


def _cmd_collect(args: argparse.Namespace) -> int:
    """Run the collect subcommand."""
    config = load_config(Path(args.config) if args.config else None)
    config = with_overrides(
        config,
        interval=args.interval,
        results=args.results,
        database=Path(args.db) if args.db else None,
    )
    db, client = _open_resources(config)
    try:
        if args.once:
            stats = collect_cycle(
                config.stations, db, client, results=config.results
            )
            print(_format_cycle(stats, next_in=None), flush=True)
            return 1 if stats.failures else 0

        print(
            f"watching {len(config.stations)} stations every "
            f"{config.interval_seconds}s -> {config.database} "
            "(Ctrl+C to stop)",
            flush=True,
        )
        try:
            while True:
                stats = collect_cycle(
                    config.stations, db, client, results=config.results
                )
                print(
                    _format_cycle(stats, next_in=config.interval_seconds),
                    flush=True,
                )
                time.sleep(config.interval_seconds)
        except KeyboardInterrupt:
            print("\ncollector stopped", flush=True)
            return 0
    finally:
        client.close()
        db.close()


def main(argv: list[str] | None = None) -> int:
    """Run the gleis404 command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return int(args.func(args))
