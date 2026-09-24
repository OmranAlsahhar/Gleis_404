"""Punctuality analysis over collected departure records."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from gleis404.client import Departure

PUNCTUALITY_THRESHOLD_SECONDS = 300
"""A delay of at most five minutes still counts as punctual."""

LOCAL_TIMEZONE = "Europe/Berlin"
"""Timezone used for hour-of-day and weekday breakdowns."""

WEEKDAY_NAMES: tuple[str, ...] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
"""Weekday labels in display order."""


def default_timezone() -> tzinfo:
    """Return the local timezone used for time-based breakdowns."""
    try:
        return ZoneInfo(LOCAL_TIMEZONE)
    except ZoneInfoNotFoundError:
        return UTC


@dataclass(frozen=True, slots=True)
class DelayStats:
    """Descriptive statistics of a set of delays (in seconds)."""

    count: int
    mean: float | None
    median: float | None
    p90: float | None
    min: int | None
    max: int | None


@dataclass(frozen=True, slots=True)
class PunctualityReport:
    """Aggregate punctuality over a set of departures."""

    total: int
    known: int
    no_realtime: int
    cancelled: int
    punctual: int
    punctuality: float | None
    delay: DelayStats


@dataclass(frozen=True, slots=True)
class GroupStats:
    """Punctuality broken down by one dimension (line, station, ...)."""

    label: str
    total: int
    known: int
    no_realtime: int
    cancelled: int
    punctual: int
    punctuality: float | None
    delay: DelayStats


def compute_delay_stats(delays: Sequence[int]) -> DelayStats:
    """Compute descriptive statistics over delays in seconds."""
    if not delays:
        return DelayStats(
            count=0,
            mean=None,
            median=None,
            p90=None,
            min=None,
            max=None,
        )
    ordered = sorted(delays)
    count = len(ordered)
    p90_index = max(0, math.ceil(0.9 * count) - 1)
    median_index = count // 2
    if count % 2:
        median = float(ordered[median_index])
    else:
        median = (ordered[median_index - 1] + ordered[median_index]) / 2
    return DelayStats(
        count=count,
        mean=sum(ordered) / count,
        median=median,
        p90=float(ordered[p90_index]),
        min=ordered[0],
        max=ordered[-1],
    )


def _known_delays(departures: Sequence[Departure]) -> list[int]:
    """Collect trustworthy delays: realtime data and no cancellation."""
    return [
        d.delay_seconds
        for d in departures
        if not d.cancelled and d.delay_seconds is not None
    ]


def summarize(departures: Sequence[Departure]) -> PunctualityReport:
    """Compute the overall punctuality report."""
    total = len(departures)
    cancelled = sum(1 for d in departures if d.cancelled)
    known_delays = _known_delays(departures)
    known = len(known_delays)
    no_realtime = total - cancelled - known
    punctual = sum(
        1 for delay in known_delays
        if delay <= PUNCTUALITY_THRESHOLD_SECONDS
    )
    punctuality = punctual / known if known else None
    return PunctualityReport(
        total=total,
        known=known,
        no_realtime=no_realtime,
        cancelled=cancelled,
        punctual=punctual,
        punctuality=punctuality,
        delay=compute_delay_stats(known_delays),
    )


def group_by(
    departures: Sequence[Departure],
    key: Callable[[Departure], str],
) -> list[GroupStats]:
    """Group departures by an arbitrary key and summarize each group."""
    buckets: dict[str, list[Departure]] = {}
    for departure in departures:
        buckets.setdefault(key(departure), []).append(departure)

    groups: list[GroupStats] = []
    for label, items in buckets.items():
        report = summarize(items)
        groups.append(
            GroupStats(
                label=label,
                total=report.total,
                known=report.known,
                no_realtime=report.no_realtime,
                cancelled=report.cancelled,
                punctual=report.punctual,
                punctuality=report.punctuality,
                delay=report.delay,
            )
        )
    return sorted(groups, key=lambda g: g.label)


def _by_volume(groups: list[GroupStats]) -> list[GroupStats]:
    """Sort groups by row count descending, label as tie-breaker."""
    return sorted(groups, key=lambda g: (-g.total, g.label))


def by_line(departures: Sequence[Departure]) -> list[GroupStats]:
    """Punctuality grouped by line, busiest line first."""
    return _by_volume(group_by(departures, lambda d: d.line))


def by_station(departures: Sequence[Departure]) -> list[GroupStats]:
    """Punctuality grouped by station, busiest station first."""
    return _by_volume(group_by(departures, lambda d: d.stop_name))


def by_hour(
    departures: Sequence[Departure], tz: tzinfo | None = None
) -> list[GroupStats]:
    """Punctuality grouped by local hour of day (00-23)."""
    zone = tz or default_timezone()
    return group_by(
        departures,
        lambda d: d.scheduled_departure.astimezone(zone).strftime("%H"),
    )


def by_weekday(
    departures: Sequence[Departure], tz: tzinfo | None = None
) -> list[GroupStats]:
    """Punctuality grouped by local weekday (Monday first)."""
    zone = tz or default_timezone()
    groups = group_by(
        departures,
        lambda d: WEEKDAY_NAMES[d.scheduled_departure.astimezone(zone).weekday()],
    )
    return sorted(
        groups, key=lambda g: WEEKDAY_NAMES.index(g.label)
    )


def by_day(
    departures: Sequence[Departure], tz: tzinfo | None = None
) -> list[GroupStats]:
    """Punctuality grouped by local calendar day."""
    zone = tz or default_timezone()
    return group_by(
        departures,
        lambda d: d.scheduled_departure.astimezone(zone).date().isoformat(),
    )


def local_window(
    departures: Sequence[Departure], tz: tzinfo | None = None
) -> tuple[datetime, datetime] | None:
    """Return the local-time span covered by the departures."""
    if not departures:
        return None
    zone = tz or default_timezone()
    times = [d.scheduled_departure for d in departures]
    return (
        min(times).astimezone(zone),
        max(times).astimezone(zone),
    )
