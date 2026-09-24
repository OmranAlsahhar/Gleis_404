"""Matplotlib/Seaborn visualizations for collected delay data."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import seaborn as sns

from gleis404.analysis import (
    PUNCTUALITY_THRESHOLD_SECONDS,
    WEEKDAY_NAMES,
    by_day,
    by_line,
    default_timezone,
)
from gleis404.client import Departure

DEFAULT_PLOTS_DIR = Path("plots")
"""Default directory for generated figures."""

THRESHOLD_MINUTES = PUNCTUALITY_THRESHOLD_SECONDS / 60
"""Punctuality threshold in minutes, drawn as the reference line."""

_PNG_DPI = 150
"""Resolution of saved figures."""


def _save(fig: matplotlib.figure.Figure, path: Path) -> Path:
    """Create parent directories, save the figure and close it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=_PNG_DPI, bbox_inches="tight")
    plt.close(fig)
    return path


def _known_delay_minutes(departures: Sequence[Departure]) -> list[float]:
    """Extract trustworthy delays as minutes."""
    return [
        d.delay_seconds / 60
        for d in departures
        if not d.cancelled and d.delay_seconds is not None
    ]


def plot_delay_distribution(
    departures: Sequence[Departure], path: str | Path
) -> Path | None:
    """Plot a histogram of realtime-confirmed delays."""
    delays = _known_delay_minutes(departures)
    if not delays:
        return None
    fig, ax = plt.subplots(figsize=(8, 5))
    bins = min(40, max(8, math.ceil(math.sqrt(len(delays)))))
    ax.hist(
        delays,
        bins=bins,
        color="#4C72B0",
        edgecolor="white",
    )
    ax.axvline(
        THRESHOLD_MINUTES,
        color="crimson",
        linestyle="--",
        linewidth=1.5,
        label=f"punctuality threshold ({THRESHOLD_MINUTES:.0f} min)",
    )
    ax.set_title(f"Delay distribution (n={len(delays)})")
    ax.set_xlabel("Delay (minutes, negative = early)")
    ax.set_ylabel("Departures")
    ax.legend(frameon=False)
    fig.tight_layout()
    return _save(fig, Path(path))


def plot_delay_heatmap(
    departures: Sequence[Departure], path: str | Path
) -> Path | None:
    """Plot a weekday × hour heatmap of mean delays (local time)."""
    zone = default_timezone()
    cells: dict[tuple[int, int], list[float]] = {}
    for departure in departures:
        if departure.cancelled or departure.delay_seconds is None:
            continue
        local = departure.scheduled_departure.astimezone(zone)
        cells.setdefault((local.weekday(), local.hour), []).append(
            departure.delay_seconds / 60
        )
    if not cells:
        return None
    weekdays = sorted({wd for wd, _ in cells})
    hours = sorted({hour for _, hour in cells})
    if len(hours) < 2 or len(weekdays) < 2:
        return None

    matrix = [
        [
            (
                sum(cells[(wd, hour)]) / len(cells[(wd, hour)])
                if (wd, hour) in cells
                else math.nan
            )
            for hour in hours
        ]
        for wd in weekdays
    ]
    fig, ax = plt.subplots(
        figsize=(max(8, 0.55 * len(hours)), max(3, 0.7 * len(weekdays)))
    )
    sns.heatmap(
        matrix,
        ax=ax,
        annot=True,
        fmt=".1f",
        cmap="RdYlGn_r",
        vmin=0,
        xticklabels=[f"{hour:02d}" for hour in hours],
        yticklabels=[WEEKDAY_NAMES[wd][:3] for wd in weekdays],
        cbar_kws={"label": "mean delay (minutes)"},
    )
    ax.set_title("Mean delay by hour and weekday (local time)")
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("")
    fig.tight_layout()
    return _save(fig, Path(path))


def plot_delay_by_line(
    departures: Sequence[Departure],
    path: str | Path,
    top_n: int = 10,
) -> Path | None:
    """Plot box charts of delays per line, busiest lines first."""
    stats = by_line(departures)
    labels = [
        group.label
        for group in stats
        if group.delay.count > 0
    ][:top_n]
    if not labels:
        return None
    lookup: dict[str, list[float]] = {label: [] for label in labels}
    for departure in departures:
        if (
            departure.line in lookup
            and not departure.cancelled
            and departure.delay_seconds is not None
        ):
            lookup[departure.line].append(departure.delay_seconds / 60)

    fig, ax = plt.subplots(
        figsize=(8, max(3.5, 0.55 * len(labels) + 1.5))
    )
    ax.boxplot(
        [lookup[label] for label in labels],
        orientation="horizontal",
        tick_labels=labels,
        patch_artist=True,
        boxprops={"facecolor": "#A6CEE3"},
        medianprops={"color": "crimson"},
    )
    ax.axvline(
        THRESHOLD_MINUTES,
        color="crimson",
        linestyle="--",
        linewidth=1.2,
        label=f"punctuality threshold ({THRESHOLD_MINUTES:.0f} min)",
    )
    ax.invert_yaxis()
    ax.set_title(f"Delay distribution by line (top {len(labels)})")
    ax.set_xlabel("Delay (minutes, negative = early)")
    ax.set_ylabel("")
    ax.legend(frameon=False)
    fig.tight_layout()
    return _save(fig, Path(path))


def plot_punctuality_trend(
    departures: Sequence[Departure], path: str | Path
) -> Path | None:
    """Plot daily mean delay and punctuality over time."""
    days = by_day(departures)
    if len(days) < 2:
        return None

    labels = [group.label for group in days]
    mean_minutes = [
        group.delay.mean / 60 if group.delay.mean is not None else math.nan
        for group in days
    ]
    punctuality = [
        group.punctuality * 100
        if group.punctuality is not None
        else math.nan
        for group in days
    ]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(
        labels,
        mean_minutes,
        marker="o",
        color="#4C72B0",
        label="mean delay (min)",
    )
    ax.set_ylabel("Mean delay (minutes)", color="#4C72B0")
    ax.tick_params(axis="x", rotation=45)

    secondary = ax.twinx()
    secondary.plot(
        labels,
        punctuality,
        marker="s",
        linestyle="--",
        color="#E31A1C",
        label="punctuality (%)",
    )
    secondary.set_ylabel("Punctuality (%)", color="#E31A1C")
    secondary.set_ylim(0, 105)

    handles_a, labels_a = ax.get_legend_handles_labels()
    handles_b, labels_b = secondary.get_legend_handles_labels()
    ax.legend(handles_a + handles_b, labels_a + labels_b, frameon=False)
    ax.set_title("Daily punctuality and mean delay")
    fig.tight_layout()
    return _save(fig, Path(path))
