"""gleis404: public transit punctuality analyzer."""

from gleis404.analysis import (
    PUNCTUALITY_THRESHOLD_SECONDS,
    DelayStats,
    GroupStats,
    PunctualityReport,
    by_day,
    by_hour,
    by_line,
    by_station,
    by_weekday,
    compute_delay_stats,
    group_by,
    local_window,
    summarize,
    timezone_label,
)
from gleis404.client import (
    Departure,
    Stop,
    TransitousAPIError,
    TransitousClient,
    parse_departure,
    parse_departures,
    parse_stop,
)
from gleis404.collector import (
    CollectorConfig,
    ConfigError,
    CycleStats,
    Station,
    collect_cycle,
    load_config,
    with_overrides,
)
from gleis404.settings import Settings, load_env, load_settings, pick
from gleis404.storage import (
    DEFAULT_DB_PATH,
    Database,
    WriteStats,
)

load_env()

__version__ = "0.1.0"

_PLOTTING_EXPORTS = frozenset(
    {
        "DEFAULT_PLOTS_DIR",
        "plot_delay_by_line",
        "plot_delay_distribution",
        "plot_delay_heatmap",
        "plot_punctuality_trend",
    }
)


def __getattr__(name: str) -> object:
    """Lazily expose gleis404.plotting members (PEP 562)."""
    if name in _PLOTTING_EXPORTS:
        from gleis404 import plotting

        return getattr(plotting, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DEFAULT_DB_PATH",
    "PUNCTUALITY_THRESHOLD_SECONDS",
    "CollectorConfig",
    "ConfigError",
    "CycleStats",
    "Database",
    "DelayStats",
    "Departure",
    "GroupStats",
    "PunctualityReport",
    "Settings",
    "Station",
    "Stop",
    "TransitousAPIError",
    "TransitousClient",
    "WriteStats",
    "__version__",
    "by_day",
    "by_hour",
    "by_line",
    "by_station",
    "by_weekday",
    "collect_cycle",
    "compute_delay_stats",
    "group_by",
    "load_config",
    "load_env",
    "load_settings",
    "local_window",
    "parse_departure",
    "parse_departures",
    "parse_stop",
    "pick",
    "plot_delay_by_line",
    "plot_delay_distribution",
    "plot_delay_heatmap",
    "plot_punctuality_trend",
    "summarize",
    "timezone_label",
    "with_overrides",
]
