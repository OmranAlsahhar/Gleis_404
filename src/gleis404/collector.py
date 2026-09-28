"""Departure collection: configuration loading and collection cycles."""

from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from collections.abc import Sequence
from dataclasses import dataclass, replace
from importlib.resources import files
from pathlib import Path

from gleis404.client import Departure, TransitousAPIError, TransitousClient
from gleis404.storage import DEFAULT_DB_PATH, Database

DEFAULT_CONFIG_NAME = "gleis404.toml"
"""Config file name looked up in the working directory."""

DEFAULT_INTERVAL_SECONDS = 300
"""Fallback collection interval (five minutes)."""

DEFAULT_RESULTS = 20
"""Fallback number of departures fetched per station and cycle."""


class ConfigError(ValueError):
    """Raised when a watchlist configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Station:
    """One stop to watch during collection."""

    id: str
    name: str


@dataclass(frozen=True, slots=True)
class CollectorConfig:
    """Collection settings loaded from TOML."""

    stations: tuple[Station, ...]
    interval_seconds: int
    database: Path
    results: int


@dataclass(frozen=True, slots=True)
class CycleStats:
    """Result of one collection cycle."""

    inserted: int
    updated: int
    failures: tuple[str, ...] = ()


def _read_toml(path: Path) -> dict:
    """Read a TOML configuration file."""
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc


def _read_builtin_config() -> dict:
    """Read the watchlist bundled with the package."""
    try:
        resource = files("gleis404").joinpath("watchlist.toml")
        return tomllib.loads(resource.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read built-in config: {exc}") from exc


def _parse_config(data: dict, source: str) -> CollectorConfig:
    """Validate raw TOML data into a CollectorConfig."""
    raw_stations = data.get("stations")
    if not isinstance(raw_stations, list) or not raw_stations:
        raise ConfigError(f"{source}: at least one [[stations]] entry required")
    stations: list[Station] = []
    for index, entry in enumerate(raw_stations):
        if not isinstance(entry, dict) or "id" not in entry:
            raise ConfigError(f"{source}: stations[{index}] needs an 'id'")
        stations.append(
            Station(
                id=str(entry["id"]),
                name=str(entry.get("name", entry["id"])),
            )
        )

    interval = data.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)
    results = data.get("results", DEFAULT_RESULTS)
    if not isinstance(interval, int) or interval <= 0:
        raise ConfigError(f"{source}: interval_seconds must be positive")
    if not isinstance(results, int) or results <= 0:
        raise ConfigError(f"{source}: results must be positive")

    database = Path(str(data.get("database", DEFAULT_DB_PATH)))
    return CollectorConfig(
        stations=tuple(stations),
        interval_seconds=interval,
        database=database,
        results=results,
    )


def load_config(path: Path | None = None) -> CollectorConfig:
    """Load the collection configuration."""
    if path is not None:
        return _parse_config(_read_toml(path), str(path))
    local = Path(DEFAULT_CONFIG_NAME)
    if local.exists():
        return _parse_config(_read_toml(local), str(local))
    return _parse_config(_read_builtin_config(), "built-in watchlist")


def _keep_watched(station: Station, departures: Sequence[Departure]) -> list[Departure]:
    """Drop departures the API attached to the station that leave from some other stop."""
    if station.name == station.id:
        return list(departures)
    return [
        departure for departure in departures if departure.stop_name == station.name
    ]


def collect_cycle(
    stations: Sequence[Station],
    db: Database,
    client: TransitousClient,
    results: int = DEFAULT_RESULTS,
) -> CycleStats:
    """Poll every station once and persist only the departures at the watched stop."""
    inserted = 0
    updated = 0
    failures: list[str] = []
    for station in stations:
        try:
            departures = client.departures(station.id, n=results)
        except TransitousAPIError as exc:
            failures.append(f"{station.name} ({exc})")
            continue
        departures = _keep_watched(station, departures)
        stats = db.insert_departures(departures)
        inserted += stats.inserted
        updated += stats.updated
    return CycleStats(inserted=inserted, updated=updated, failures=tuple(failures))


def with_overrides(
    config: CollectorConfig,
    interval: int | None = None,
    results: int | None = None,
    database: Path | None = None,
) -> CollectorConfig:
    """Return a copy of the config with CLI-style overrides applied."""
    return replace(
        config,
        interval_seconds=interval if interval is not None else config.interval_seconds,
        results=results if results is not None else config.results,
        database=database if database is not None else config.database,
    )
