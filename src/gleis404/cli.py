"""Command-line interface for gleis404."""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gleis404 import __version__
from gleis404.analysis import (
    GroupStats,
    PunctualityReport,
    by_day,
    by_hour,
    by_line,
    by_station,
    by_weekday,
    default_timezone,
    departed,
    local_window,
    summarize,
    timezone_label,
)
from gleis404.client import Departure, TransitousClient
from gleis404.collector import (
    CollectorConfig,
    CycleStats,
    collect_cycle,
    load_config,
    with_overrides,
)
from gleis404.settings import Settings, load_settings, pick
from gleis404.storage import Database

__all__ = [
    "build_parser",
    "main",
]


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser for the gleis404 CLI."""
    parser = argparse.ArgumentParser(
        prog="gleis404",
        description=(
            "Collect realtime public transit departures and analyze punctuality trends."
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

    stats_parser = subparsers.add_parser(
        "stats",
        help="print punctuality statistics for collected departures",
        description=(
            "Analyze the collected departures: overall punctuality "
            "plus breakdowns by station, line, hour, weekday and day. "
            "Only realtime-confirmed delays are counted."
        ),
    )
    _add_data_args(stats_parser)
    stats_parser.add_argument(
        "--top",
        type=int,
        default=None,
        metavar="N",
        help="lines to show in the by-line table (default: GLEIS404_TOP or 10)",
    )
    stats_parser.set_defaults(func=_cmd_stats)

    plot_parser = subparsers.add_parser(
        "plot",
        help="save delay visualizations as PNG files",
        description=(
            "Generate delay distribution, heatmap, per-line box chart "
            "and daily trend figures from the collected departures "
            "and save them as PNG files."
        ),
    )
    _add_data_args(plot_parser)
    plot_parser.add_argument(
        "--outdir",
        metavar="DIR",
        help="directory for generated PNGs (default: GLEIS404_PLOTS_DIR or plots)",
    )
    plot_parser.add_argument(
        "--top",
        type=int,
        default=None,
        metavar="N",
        help="lines to include in the by-line chart (default: GLEIS404_TOP or 10)",
    )
    plot_parser.set_defaults(func=_cmd_plot)
    return parser


def _add_data_args(parser: argparse.ArgumentParser) -> None:
    """Add the database and filter options shared by data subcommands."""
    parser.add_argument(
        "--db",
        metavar="PATH",
        help="SQLite database path instead of the configured one",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="watchlist TOML to resolve the default database path from",
    )
    parser.add_argument(
        "--line",
        metavar="LINE",
        help="only analyze this line (case-insensitive exact match)",
    )
    parser.add_argument(
        "--stop",
        metavar="NAME",
        help="only analyze stations whose name contains this text",
    )
    parser.add_argument(
        "--since",
        type=_parse_day,
        metavar="YYYY-MM-DD",
        help="only analyze departures from this date (inclusive)",
    )
    parser.add_argument(
        "--until",
        type=_parse_until_day,
        metavar="YYYY-MM-DD",
        help="only analyze departures up to this date (inclusive)",
    )


def _parse_day(value: str, *, end_of_range: bool = False) -> datetime:
    """Parse a YYYY-MM-DD date into a local-time range boundary."""
    tz = default_timezone()
    try:
        boundary = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=tz)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r}, expected YYYY-MM-DD"
        ) from exc
    return boundary + timedelta(days=1) if end_of_range else boundary


def _parse_until_day(value: str) -> datetime:
    """Parse an --until date into an exclusive next-midnight bound."""
    return _parse_day(value, end_of_range=True)


def _format_cycle(stats: CycleStats, next_in: int | None) -> str:
    """Render one cycle's result as a log line."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
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


def _resolve_db(
    args: argparse.Namespace, settings: Settings, config: CollectorConfig
) -> Path:
    """Pick the database path: CLI flag, then .env, then the TOML."""
    chosen = pick(
        Path(args.db) if args.db else None, settings.database, config.database
    )
    assert chosen is not None
    return chosen


def _resolve_top(value: int | None, settings: Settings) -> int:
    """Pick the by-line limit: CLI flag, then .env, then 10."""
    return max(1, pick(value, settings.top, 10) or 10)


def _cmd_collect(args: argparse.Namespace) -> int:
    """Run the collect subcommand."""
    settings = load_settings()
    config = load_config(Path(args.config) if args.config else None)
    config = with_overrides(
        config,
        interval=pick(args.interval, settings.interval_seconds),
        results=pick(args.results, settings.results),
        database=Path(args.db) if args.db else settings.database,
    )
    db, client = _open_resources(config)
    try:
        if args.once:
            stats = collect_cycle(config.stations, db, client, results=config.results)
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


def _fmt_pct(value: float | None) -> str:
    """Format a punctuality ratio as a percentage."""
    return "—" if value is None else f"{value * 100:.1f}%"


def _fmt_minutes(seconds: float | None) -> str:
    """Format a delay in seconds as minutes."""
    return "—" if seconds is None else f"{seconds / 60:.1f}"


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Render a left-aligned text table."""
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows))
        if rows
        else len(headers[i])
        for i in range(len(headers))
    ]
    header_line = (
        headers[0].ljust(widths[0])
        + "  "
        + "  ".join(
            title.rjust(widths[i]) for i, title in enumerate(headers[1:], start=1)
        )
    )
    rule = "  ".join("-" * width for width in widths)
    body = [
        row[0].ljust(widths[0])
        + "  "
        + "  ".join(cell.rjust(widths[i]) for i, cell in enumerate(row[1:], start=1))
        for row in rows
    ]
    return [header_line, rule, *body]


def _group_table(title: str, groups: list[GroupStats]) -> list[str]:
    """Render one breakdown section."""
    rows = [
        [
            group.label,
            str(group.total),
            _fmt_pct(group.punctuality),
            _fmt_minutes(group.delay.mean),
            _fmt_minutes(group.delay.median),
            _fmt_minutes(group.delay.p90),
        ]
        for group in groups
    ]
    table = _table(["", "n", "punct%", "mean", "median", "p90"], rows)
    return [title, *table, ""]


def _render_report(
    report: PunctualityReport,
    stations: list[GroupStats],
    lines: list[GroupStats],
    hours: list[GroupStats],
    weekdays: list[GroupStats],
    days: list[GroupStats],
    window: tuple[datetime, datetime] | None,
    top_lines: int,
) -> str:
    """Render the full punctuality report for terminal output."""
    out: list[str] = ["gleis404 punctuality report", "=" * 70]
    if window is not None:
        out.append(
            f"window   : {window[0]:%Y-%m-%d %H:%M} → "
            f"{window[1]:%Y-%m-%d %H:%M} ({timezone_label()})"
        )
    out.append(
        f"records  : {report.total} total | {report.known} with realtime "
        f"delay | {report.no_realtime} no realtime data | "
        f"{report.cancelled} cancelled"
    )
    if report.punctuality is None:
        out.append("punctual : n/a — no realtime data available")
    else:
        out.append(
            f"punctual : {_fmt_pct(report.punctuality)} "
            f"({report.punctual}/{report.known} within 5 min late)"
        )
    delay = report.delay
    if delay.count:
        out.append(
            f"delay    : mean {_fmt_minutes(delay.mean)} min | "
            f"median {_fmt_minutes(delay.median)} | "
            f"p90 {_fmt_minutes(delay.p90)} | "
            f"min {_fmt_minutes(delay.min)} | "
            f"max {_fmt_minutes(delay.max)}"
        )
    else:
        out.append("delay    : n/a — no realtime data available")

    out.append("")
    out.extend(_group_table("by station (busiest first)", stations))
    shown = lines[:top_lines]
    out.extend(_group_table(f"by line (top {len(shown)} of {len(lines)})", shown))
    out.extend(_group_table("by hour of day (local time)", hours))
    out.extend(_group_table("by weekday", weekdays))
    out.extend(_group_table("by day", days))
    return "\n".join(out)


def _filter_departures(
    departures: list[Departure],
    args: argparse.Namespace,
) -> list[Departure]:
    """Apply the stats/plot filter options to loaded departures."""
    if not args.until:
        departures = departed(departures)
    if args.line:
        wanted = args.line.casefold()
        departures = [d for d in departures if d.line.casefold() == wanted]
    if args.stop:
        needle = args.stop.casefold()
        departures = [d for d in departures if needle in d.stop_name.casefold()]
    if args.since:
        departures = [d for d in departures if d.scheduled_departure >= args.since]
    if args.until:
        departures = [d for d in departures if d.scheduled_departure < args.until]
    return departures


def _cmd_stats(args: argparse.Namespace) -> int:
    """Run the stats subcommand."""
    settings = load_settings()
    config = load_config(Path(args.config) if args.config else None)
    db_path = _resolve_db(args, settings, config)
    with Database(db_path) as db:
        departures = db.query_departures()
    departures = _filter_departures(departures, args)

    if not departures:
        print("No departures match. Run 'uv run -m gleis404 collect --once' first.")
        return 1

    print(
        _render_report(
            report=summarize(departures),
            stations=by_station(departures),
            lines=by_line(departures),
            hours=by_hour(departures),
            weekdays=by_weekday(departures),
            days=by_day(departures),
            window=local_window(departures),
            top_lines=_resolve_top(args.top, settings),
        )
    )
    return 0


def _cmd_plot(args: argparse.Namespace) -> int:
    """Run the plot subcommand."""
    settings = load_settings()
    config = load_config(Path(args.config) if args.config else None)
    db_path = _resolve_db(args, settings, config)
    with Database(db_path) as db:
        departures = db.query_departures()
    departures = _filter_departures(departures, args)
    if not departures:
        print("No departures match. Run 'uv run -m gleis404 collect --once' first.")
        return 1

    from gleis404.plotting import (
        DEFAULT_PLOTS_DIR,
        plot_delay_by_line,
        plot_delay_distribution,
        plot_delay_heatmap,
        plot_punctuality_trend,
    )

    outdir = (
        pick(Path(args.outdir) if args.outdir else None, settings.plots_dir)
        or DEFAULT_PLOTS_DIR
    )
    top = _resolve_top(args.top, settings)
    jobs: dict[str, Callable[[Path], Path | None]] = {
        "delay_distribution.png": lambda p: plot_delay_distribution(departures, p),
        "delay_heatmap.png": lambda p: plot_delay_heatmap(departures, p),
        "delay_by_line.png": lambda p: plot_delay_by_line(departures, p, top_n=top),
        "punctuality_trend.png": lambda p: plot_punctuality_trend(departures, p),
    }
    saved: list[Path] = []
    skipped: list[str] = []
    for filename, job in jobs.items():
        result = job(outdir / filename)
        if result is None:
            skipped.append(filename)
        else:
            saved.append(result)
            print(f"saved     {result}")
    for filename in skipped:
        print(f"skipped   {filename} (not enough data for this figure)")
    if not saved:
        print("No figure could be generated from the available data.")
        return 1
    print(f"{len(saved)} figure(s) written to {outdir}/")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the gleis404 command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return int(args.func(args))
