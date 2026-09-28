# gleis404

**gleis404** is a command-line tool that quietly logs realtime public
transit departures in Dortmund every five minutes, stores the delay
history in SQLite, and turns it into punctuality statistics and
figures — *how punctual is the local transit, really, and when is it
worst?*

Named after a track that doesn't exist (`Gleis 404`).

## Features

- **Continuous collection** — polls four Dortmund stops every five
  minutes via the free [Transitous](https://transitous.org/) API and
  upserts each service run's latest realtime status (delays,
  cancellations) into SQLite.
- **Honest statistics** (`stats`) — only realtime-confirmed delays are
  counted; records without realtime data are reported separately as
  *unknown* and never inflate the punctuality score. Cancelled trips
  are excluded from delay math and reported on their own.
- **Breakdowns** by station, line, local hour of day, weekday and day.
- **Visualizations** (`plot`) — delay distribution, weekday × hour
  heatmap, per-line box charts and the daily trend, saved as PNG files
  to `plots/` (never just displayed).
- **Demo notebook** — [`notebooks/demo.ipynb`](notebooks/demo.ipynb)
  walks through the whole workflow as a library user.

## Requirements

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) (used for everything: deps, lock
  file, running)

## Installation

```bash
git clone https://github.com/OmranAlsahhar/Gleis_404.git
cd Gleis_404
uv sync                      # create .venv from uv.lock (includes dev tools)
```

Prefer an editable install? That works too:

```bash
uv pip install -e .
```

## Usage

All commands run through `uv run`:

```bash
# one collection cycle (fetches the next departures at all watchlist stops)
uv run -m gleis404 collect --once

# continuous collection: every 300 s (Ctrl+C to stop)
uv run -m gleis404 collect

# punctuality report with breakdowns
uv run -m gleis404 stats

# filtered: one line, one station, a date range
uv run -m gleis404 stats --line U41 --since 2026-09-23 --until 2026-09-30

# generate the figures in plots/
uv run -m gleis404 plot
```

Example output of `uv run -m gleis404 stats`:

```text
gleis404 punctuality report
======================================================================
window   : 2026-09-23 10:48 → 2026-09-23 12:09 (Europe/Berlin)
records  : 207 total | 183 with realtime delay | 23 no realtime data | 0 cancelled
punctual : 94.5% (173/183 within 5 min late)
delay    : mean 0.9 min | median 0.0 | p90 2.0 | min -7.0 | max 25.0

by station (busiest first)
                               n  punct%  mean  median    p90
----------------------------  --  ------  ----  ------  ----
Dortmund Hbf                  69   90.3%   1.5     0.0   5.0
...
```

Figures are written to files and referenced below (they are committed
to the repository):

| Figure | File |
|---|---|
| Delay distribution | [`plots/delay_distribution.png`](plots/delay_distribution.png) |
| Delay by line (box charts) | [`plots/delay_by_line.png`](plots/delay_by_line.png) |
| Weekday × hour heatmap | [`plots/delay_heatmap.png`](plots/delay_heatmap.png) |
| Daily punctuality trend | [`plots/punctuality_trend.png`](plots/punctuality_trend.png) |

The heatmap and trend render only once the data spans at least two
weekdays/two days respectively — until then `plot` reports them as
*skipped* rather than drawing an empty chart.

## Configuration

The default watchlist is bundled at
[`src/gleis404/watchlist.toml`](src/gleis404/watchlist.toml)
(Dortmund Hbf, An der Palmweide, Universität, Stadtgarten). To watch
other stops, copy the file, edit the `[[stations]]` entries
(`id` = Transitous stop ID, `name` = display name), and pass it:

```bash
uv run -m gleis404 collect --config my-watchlist.toml
uv run -m gleis404 stats   --config my-watchlist.toml
```

Resolution order for the config file: `--config PATH` → `./gleis404.toml` → built-in
default. Other options: `--interval SECONDS`, `--results N`, `--db PATH`.

### Environment settings (`.env`)

Everything that is a plain knob rather than structured data lives in a
`.env` file, so reconfiguring the tool never requires editing code:

```bash
cp .env.example .env     # then adjust the values
```

| Variable | Controls | Default |
|---|---|---|
| `GLEIS404_INTERVAL_SECONDS` | seconds between collection cycles (e.g. `60` = every minute) | `300` |
| `GLEIS404_RESULTS` | departures fetched per station per cycle | `20` |
| `GLEIS404_DATABASE` | SQLite database path | `data/gleis404.db` |
| `GLEIS404_PLOTS_DIR` | figure output directory | `plots` |
| `GLEIS404_TOP` | lines shown in the by-line table/chart | `10` |
| `GLEIS404_API_BASE_URL` | Transitous API endpoint | `https://api.transitous.org` |
| `GLEIS404_USER_AGENT` | User-Agent identifying you to Transitous | GitHub URL |
| `GLEIS404_TIMEOUT` | HTTP request timeout (seconds) | `15` |
| `GLEIS404_TIMEZONE` | timezone for hour/weekday analysis | `Europe/Berlin` |

**Layering (highest wins):** CLI flags → `.env` → `watchlist.toml` →
built-in defaults. Real process environment variables always beat the
file (systemd and friends stay in control), and a blank or invalid
value is ignored with a warning and falls back to the next layer — a
typo can never break collection. The stations themselves are
structured data and stay in the TOML watchlist.

`.env` is gitignored because it may contain your contact details in
the User-Agent; the commented [``.env.example``](.env.example) is
committed in its place. Restart the collector after changing it, since
settings are read at startup.

## Methodology

- A delay exists **only** if the feed confirms realtime data for the
  departure (`real_time=True`); otherwise it is recorded and counted
  as *unknown* — `0` always means "confirmed punctual".
- **Not-yet-departed trips are excluded.** The feed already publishes
  the rest of the day's timetable with a prediction equal to the
  schedule; a trip that has not left yet cannot be judged, so
  `stats` and `plot` only evaluate departures whose scheduled time
  has passed (an explicit `--until` overrides this).
- A departure counts as **punctual** if it leaves ≤ 5 minutes late
  (early departures count as punctual).
- **Cancelled** trips are excluded from delay statistics and reported
  separately.
- Hour/weekday breakdowns use **Europe/Berlin** local time (override
  with `GLEIS404_TIMEZONE`), because rush-hour patterns are
  meaningless in UTC.
- Re-collected departures are **upserted** on
  `(trip_id, stop_id, scheduled_departure)`, so each row always holds
  the most recently observed status — one row per service run.

## Project structure

```text
gleis404/
├── pyproject.toml          # hatchling build backend, uv-managed deps
├── .env.example            # documented .env template (copy to .env)
├── src/gleis404/
│   ├── __init__.py         # public API (re-exports + lazy plotting)
│   ├── __main__.py         # entry point: uv run -m gleis404
│   ├── cli.py              # argparse subcommands: collect, stats, plot
│   ├── client.py           # Transitous API client + typed Departure
│   ├── collector.py        # watchlist config + collection cycles
│   ├── settings.py         # .env configuration with safe fallbacks
│   ├── storage.py          # SQLite schema, upserts, queries
│   ├── analysis.py         # pure punctuality statistics
│   ├── plotting.py         # matplotlib/seaborn PNG figures
│   └── watchlist.toml      # default four Dortmund stops
├── notebooks/demo.ipynb    # executed walkthrough
├── data/gleis404.db        # collected delay history (bundled)
└── plots/*.png             # generated figures (committed)
```

## Using it as a library

Everything useful is exposed at the package root:

```python
from gleis404 import Database, TransitousClient, summarize, by_line

with TransitousClient() as client:
    stops = client.geocode("Dortmund Hbf")
    departures = client.departures(stops[0].id, n=20)

with Database("data/gleis404.db") as db:
    db.insert_departures(departures)
    report = summarize(db.query_departures())
    print(report.punctuality)
```

## Development

```bash
uv run ruff check        # lint
uv run ruff format       # format
uv run jupyter execute notebooks/demo.ipynb --inplace   # re-run the notebook
```

## Data source

Departure data is provided by
[Transitous](https://transitous.org/) ([sources](
https://transitous.org/sources/)), which is built on openly available
GTFS/GTFS-RT feeds and [OpenStreetMap](https://www.openstreetmap.org/copyright)
data; gleis404 sends a descriptive `User-Agent` as required by the
Transitous usage policy.
