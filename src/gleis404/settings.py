"""Environment-backed settings loaded from a .env file."""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

ENV_FILE_NAME = ".env"
"""Environment file, found in the working directory or any parent."""

ENV_PREFIX = "GLEIS404_"
"""Prefix of every configuration environment variable."""

ENV_VAR_NAMES: tuple[str, ...] = (
    "INTERVAL_SECONDS",
    "RESULTS",
    "DATABASE",
    "PLOTS_DIR",
    "TOP",
    "API_BASE_URL",
    "USER_AGENT",
    "TIMEOUT",
    "TIMEZONE",
)
"""All recognized configuration variables (without the prefix)."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Resolved .env configuration."""

    interval_seconds: int | None = None
    results: int | None = None
    database: Path | None = None
    plots_dir: Path | None = None
    top: int | None = None
    api_base_url: str | None = None
    user_agent: str | None = None
    timeout: float | None = None
    timezone: str | None = None


def load_env(path: Path | None = None) -> None:
    """Load a .env file into os.environ if it exists."""
    if path is not None:
        target = path
    else:
        target = next(
            (
                directory / ENV_FILE_NAME
                for directory in (Path.cwd(), *Path.cwd().parents)
                if (directory / ENV_FILE_NAME).is_file()
            ),
            Path(ENV_FILE_NAME),
        )
    if target.is_file():
        load_dotenv(target, override=False)


def _raw(name: str) -> str | None:
    """Read one prefixed environment variable, treating blanks as unset."""
    value = os.environ.get(f"{ENV_PREFIX}{name}")
    if value is None:
        return None
    value = value.strip()
    return value or None


def _warn(name: str, reason: str) -> None:
    """Warn that an environment variable is being ignored."""
    warnings.warn(
        f"{ENV_PREFIX}{name} {reason}; ignoring it",
        UserWarning,
        stacklevel=3,
    )


def _positive_int(name: str) -> int | None:
    """Parse a positive-integer environment variable."""
    raw = _raw(name)
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        _warn(name, f"must be an integer, got {raw!r}")
        return None
    if value <= 0:
        _warn(name, f"must be positive, got {raw!r}")
        return None
    return value


def _positive_float(name: str) -> float | None:
    """Parse a positive-float environment variable."""
    raw = _raw(name)
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        _warn(name, f"must be a number, got {raw!r}")
        return None
    if value <= 0:
        _warn(name, f"must be positive, got {raw!r}")
        return None
    return value


def _path(name: str) -> Path | None:
    """Parse a filesystem-path environment variable."""
    raw = _raw(name)
    return Path(raw).expanduser() if raw is not None else None


def _base_url(name: str = "API_BASE_URL") -> str | None:
    """Parse the API base URL, requiring an http(s) scheme."""
    raw = _raw(name)
    if raw is None:
        return None
    if not raw.startswith(("http://", "https://")):
        _warn(name, f"must start with http:// or https://, got {raw!r}")
        return None
    return raw


def _timezone(name: str = "TIMEZONE") -> str | None:
    """Parse an IANA timezone name, verified against the tz database."""
    raw = _raw(name)
    if raw is None:
        return None
    try:
        ZoneInfo(raw)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        _warn(name, f"is not a known timezone, got {raw!r}")
        return None
    return raw


def load_settings() -> Settings:
    """Read all configuration variables from the environment."""
    return Settings(
        interval_seconds=_positive_int("INTERVAL_SECONDS"),
        results=_positive_int("RESULTS"),
        database=_path("DATABASE"),
        plots_dir=_path("PLOTS_DIR"),
        top=_positive_int("TOP"),
        api_base_url=_base_url(),
        user_agent=_raw("USER_AGENT"),
        timeout=_positive_float("TIMEOUT"),
        timezone=_timezone(),
    )


def pick[T](*candidates: T | None) -> T | None:
    """Return the first non-None candidate."""
    for candidate in candidates:
        if candidate is not None:
            return candidate
    return None
