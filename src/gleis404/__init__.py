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
from gleis404.storage import (
    DEFAULT_DB_PATH,
    Database,
    WriteStats,
)

__version__ = "0.1.0"

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
    "local_window",
    "parse_departure",
    "parse_departures",
    "parse_stop",
    "summarize",
    "with_overrides",
]
