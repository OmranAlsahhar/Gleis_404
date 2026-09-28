"""HTTP client for the free Transitous (MOTIS) public transport API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from typing_extensions import Self

from gleis404.settings import load_settings, pick

DEFAULT_BASE_URL = "https://api.transitous.org"
DEFAULT_USER_AGENT = "gleis404/0.1.0 (https://github.com/OmranAlsahhar/Gleis_404)"


class TransitousAPIError(Exception):
    """Raised when the Transitous API cannot be reached or returns an error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Store the error message and optional HTTP status code."""
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class Stop:
    """A transit stop or station resolved by the geocoder."""

    id: str
    """Transitous stop ID, usable as ``stopId`` for departure queries."""

    name: str
    """Display name of the stop, e.g. ``"Dortmund Hbf"``."""

    lat: float
    """Latitude in degrees."""

    lon: float
    """Longitude in degrees."""

    country: str | None
    """ISO country code, if provided by the API."""

    zip: str | None
    """Postal code, if provided by the API."""

    timezone: str | None
    """IANA timezone, if provided by the API."""


@dataclass(frozen=True, slots=True)
class Departure:
    """A single scheduled departure at a stop, with realtime status."""

    trip_id: str
    """Unique identifier of the trip; together with the scheduled time it
    identifies one service run for deduplication."""

    stop_id: str
    """Stop ID where this departure occurs."""

    stop_name: str
    """Display name of the stop."""

    line: str
    """Line name, e.g. ``"U41"``, ``"S5"`` or ``"RE6"`` — the route
    short name, falling back to the display name."""

    mode: str
    """Transport mode, e.g. ``"SUBWAY"``, ``"BUS"``, ``"REGIONAL_RAIL"``."""

    headsign: str | None
    """Final destination / direction of the trip, if known."""

    scheduled_departure: datetime
    """Timetabled departure time (timezone-aware)."""

    departure: datetime | None
    """Best-known departure time including realtime updates, if known."""

    delay_seconds: int | None
    """Delay in seconds relative to the timetable. ``None`` whenever the
    feed carries no realtime information for this departure, so that
    ``0`` always means "confirmed punctual" rather than "unknown"."""

    real_time: bool
    """Whether the API provided realtime data for this departure."""

    cancelled: bool
    """Whether this departure (or its whole trip) is cancelled."""

    track: str | None
    """Current track/platform, if known."""

    scheduled_track: str | None
    """Timetabled track/platform, if known."""


def parse_stop(payload: dict[str, Any]) -> Stop:
    """Parse one geocoder result into a Stop."""
    return Stop(
        id=str(payload["id"]),
        name=str(payload["name"]),
        lat=float(payload["lat"]),
        lon=float(payload["lon"]),
        country=payload.get("country"),
        zip=payload.get("zip"),
        timezone=payload.get("tz"),
    )


def _parse_time(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (...Z allowed) into aware datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_departure(payload: dict[str, Any]) -> Departure | None:
    """Parse one stoptime entry into a Departure."""
    place: dict[str, Any] = payload["place"]
    scheduled = _parse_time(place.get("scheduledDeparture"))
    if scheduled is None:
        return None
    actual = _parse_time(place.get("departure"))

    real_time = bool(payload.get("realTime"))
    delay: int | None = None
    if real_time and actual is not None:
        delay = int((actual - scheduled).total_seconds())

    cancelled = bool(
        payload.get("cancelled")
        or payload.get("tripCancelled")
        or place.get("cancelled")
    )

    line = payload.get("routeShortName") or payload.get("displayName") or ""
    return Departure(
        trip_id=str(payload.get("tripId", "")),
        stop_id=str(place.get("stopId", "")),
        stop_name=str(place.get("name", "")),
        line=str(line),
        mode=str(payload.get("mode", "")),
        headsign=payload.get("headsign"),
        scheduled_departure=scheduled,
        departure=actual,
        delay_seconds=delay,
        real_time=real_time,
        cancelled=cancelled,
        track=place.get("track"),
        scheduled_track=place.get("scheduledTrack"),
    )


def parse_departures(payload: dict[str, Any]) -> list[Departure]:
    """Parse a stoptimes response into a list of departures."""
    return [
        parsed
        for item in payload.get("stopTimes", [])
        if (parsed := parse_departure(item)) is not None
    ]


class TransitousClient:
    """Synchronous HTTP client for the Transitous MOTIS API."""

    def __init__(
        self,
        base_url: str | None = None,
        user_agent: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Create a client."""
        settings = load_settings()
        self._client = httpx.Client(
            base_url=pick(base_url, settings.api_base_url, DEFAULT_BASE_URL),
            headers={
                "User-Agent": pick(user_agent, settings.user_agent, DEFAULT_USER_AGENT)
            },
            timeout=pick(timeout, settings.timeout, 15.0),
            transport=transport,
        )

    def geocode(self, query: str, limit: int | None = None) -> list[Stop]:
        """Resolve a free-text station query to transit stops."""
        data = self._get_json("/api/v1/geocode", {"text": query})
        stops = [
            parse_stop(item)
            for item in data
            if isinstance(item, dict) and item.get("type") == "STOP"
        ]
        return stops if limit is None else stops[:limit]

    def departures(self, stop_id: str, n: int = 20) -> list[Departure]:
        """Fetch the next departures at a stop, including realtime delays."""
        data = self._get_json("/api/v6/stoptimes", {"stopId": stop_id, "n": n})
        return parse_departures(data)

    def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        """Perform a GET request and return the decoded JSON body."""
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise TransitousAPIError(f"request to {path} failed: {exc}") from exc
        if response.status_code != 200:
            raise TransitousAPIError(
                f"request to {path} returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise TransitousAPIError(
                f"request to {path} returned invalid JSON"
            ) from exc
        if isinstance(data, dict) and "error" in data:
            raise TransitousAPIError(
                f"API error for {path}: {data['error']}",
                status_code=response.status_code,
            )
        return data

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> Self:
        """Enter a context manager; returns this client."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Exit the context manager, closing the connection pool."""
        self.close()
