# Section23 Jobs

Async Python aggregator for French job offers: multi-source ingest, dedup, LLM scoring, alerts and a web board.

## Problem

French job offers are spread across several channels: the France Travail API (the public employment service), aggregators such as Adzuna, and RSS feeds from smaller boards. Covering them by hand means running the same searches in each one, seeing the same offer more than once, and still reading every result to decide whether it fits.

This service runs that loop on a schedule. It polls each configured source, normalizes offers into one schema, drops duplicates (same URL, or near-identical title and company within 7 days), optionally asks an LLM to score each new offer from 1 to 10 against a free-text target profile, and pushes offers scored at or above a threshold to Telegram and/or Discord. A small authenticated web board lets several users browse the same pool by job family (a named group of keywords), region or distance, and mark offers as viewed, saved or dismissed.

[TODO: who it was built for and how it is used day to day]

## Architecture

Two processes share one PostgreSQL database and nothing else: the aggregator (scheduler, sources, scoring, notifications, geocoding) and the web app (FastAPI + Jinja2).

```mermaid
flowchart LR
  subgraph EXT["External services"]
    FT["France Travail API"]
    AZ["Adzuna API"]
    RSS["RSS feeds"]
    OAI["OpenAI API"]
    TG["Telegram"]
    DC["Discord"]
    NOM["Nominatim (OSM)"]
  end

  subgraph AGG["Aggregator process: python -m job_aggregator.main"]
    SCH["Scheduler<br/>main.py, scheduler/jobs.py"]
    SRC["Source adapters<br/>sources/*"]
    KW["Keyword pre-filter<br/>filters/keywords.py"]
    DD["Dedup + insert<br/>filters/dedup.py, db/repository.py"]
    SC["LLM scorer<br/>filters/scorer.py"]
    NT["Notifiers<br/>notifier/*"]
    GEO["Geocoder<br/>geocoder.py"]
    CLN["Expiry cleanup<br/>scheduler/jobs.py"]
  end

  subgraph WEB["Web process: uvicorn job_aggregator.webapp.app:app"]
    APP["FastAPI routers + Jinja2 pages<br/>webapp/*"]
  end

  DB[("PostgreSQL<br/>db/models.py")]
  USER["Browser"]

  FT --> SRC
  AZ --> SRC
  RSS --> SRC
  SCH -->|"fetch jobs"| SRC
  SRC -->|"RawOffer"| KW
  KW --> DD
  DD --> DB
  SCH -->|"score_and_notify"| SC
  DB -->|"unscored offers"| SC
  SC <--> OAI
  SC -->|"score + reason"| DB
  DB -->|"score at or above threshold"| NT
  NT --> TG
  NT --> DC
  SCH -->|"geocode_offers"| GEO
  GEO <--> NOM
  GEO --> DB
  SCH -->|"every 24 h"| CLN
  CLN --> DB
  USER <--> APP
  APP <--> DB
```

- **Scheduler** (`src/job_aggregator/main.py`, `src/job_aggregator/scheduler/jobs.py`): registers only the sources whose settings are non-empty, then runs APScheduler interval jobs: France Travail every 120 min, RSS every 30, Adzuna every 60, score-and-notify every 5, geocoding every 10, expired-offer cleanup every 24 h (currently a no-op, see Status and limitations). Each interval schedule first fires at startup (APScheduler 4 `IntervalTrigger` default, checked against 4.0.0a6), and `main.py:102-107` queues one more fetch per enabled source, so each source is fetched twice at boot.
- **Source adapters** (`src/job_aggregator/sources/`): every adapter returns a normalized `RawOffer` (`base.py`). `france_travail.py` does OAuth2 client-credentials with token refresh 30 s before expiry and one retry on 401, paginates in 150-offer ranges, and sends one query per keyword. `adzuna.py` reads up to 3 pages of 50. `rss.py` parses feeds with feedparser and strips HTML from summaries.
- **Keyword pre-filter** (`src/job_aggregator/filters/keywords.py`): case-insensitive substring checks on sector keywords (title + description) and location, and a case-insensitive exact match on contract type. An offer with no location or contract data passes.
- **Dedup + insert** (`src/job_aggregator/filters/dedup.py`, `src/job_aggregator/db/repository.py`): fuzzy check on title + company against the last 7 days (rapidfuzz `token_sort_ratio` >= 85), then an insert keyed on the SHA-256 of the URL with `ON CONFLICT DO NOTHING`.
- **LLM scorer** (`src/job_aggregator/filters/scorer.py`): sends the target profile and the offer (description truncated to 2,000 characters) to an OpenAI chat model, expects a JSON object `{"score", "reason"}`, and clamps the score to 1-10.
- **Notifiers** (`src/job_aggregator/notifier/`): Telegram (MarkdownV2 message) and Discord (embed colored by score), up to 3 attempts per channel. The final outcome per channel (success, or the error) is written to `notification_log`.
- **Geocoder** (`src/job_aggregator/geocoder.py`): fills coordinates for offers that have a location string but no lat/lon, 20 per run, through Nominatim with a 1.1 s pause between lookups. Results, including failures, are cached in `geo_cache` by accent-stripped, lowercased location.
- **Database** (`src/job_aggregator/db/engine.py`, `src/job_aggregator/db/models.py`): SQLAlchemy 2 async with asyncpg. Eight tables: `job_offers`, `job_families`, `job_family_keywords`, `region_anchors`, `geo_cache`, `users`, `offer_views`, `notification_log`.
- **Web app** (`src/job_aggregator/webapp/`): username/password login (bcrypt) with a signed 7-day session cookie, `HttpOnly`, `SameSite=Lax` and `Secure` by default (`auth.py`). The web process refuses to start if `WEBAPP_SECRET` is empty or still the `.env.example` placeholder; a JSON API for offers, families, regions, users and per-user view status (`routers/`); server-rendered pages plus vanilla JS (`templates/`, `static/`). Admin-only routes manage families, regions and users. The UI is in French.
- **Scripts** (`scripts/`): `create_admin.py` creates an admin user (password read without echo); `seed_data.py` creates four job families with French keyword lists (BNSSA lifeguards, VRD masonry and road works, warehouse forklift drivers, retail unit managers) and one region anchor per French département (101). Re-running it only adds what is missing.

## Technical choices and trade-offs

1. **In-process scheduler instead of a queue and workers.** Fetching (one schedule per source), score-and-notify, geocoding and cleanup are separate interval jobs inside one asyncio process (`main.py:51-98`), so the aggregator is a single container. Cost: it depends on a pre-release (`apscheduler>=4.0.0a5`, `pyproject.toml:12`); the scheduler is created with no data store (`main.py:51`), so schedules are rebuilt on every start; each source is fetched twice at boot, once by its schedule's first fire and once by the extra job queued in `main.py:102-107`; nothing coordinates two aggregator replicas.
2. **Fuzzy dedup first, exact URL hash second.** The same offer reposted on another source has a different URL, so title + company similarity over a 7-day window catches it (`repository.py:49-65`); the unique `url_hash` plus `ON CONFLICT DO NOTHING` makes re-fetching idempotent (`repository.py:21-46`, `models.py:33`). Cost: the fuzzy check runs first and loads every offer from the last 7 days into Python for each incoming offer, so a poll does O(new x window) comparisons. Location is not part of the key, so one employer posting the same title in several cities is kept once.
3. **Scoring decoupled from ingestion.** Ingestion needs no LLM key and stays fast; a separate job scores the 20 oldest unscored offers every 5 minutes at temperature 0.1 with a 100-token cap (`jobs.py:89-109`, `scorer.py:44-57`). Cost: with defaults, throughput is capped at 240 offers per hour. Any scoring failure stores `(5, "scoring_error")` (`scorer.py:71-73`), which is below the default threshold of 7 and is never retried, so an API outage quietly removes those offers from alerts. Notifications only consider scored offers (`repository.py:79-92`), so no OpenAI key means no alerts.
4. **One France Travail query per keyword.** Space-separated terms in `motsCles` are combined with AND (`france_travail.py:187-188`), so OR semantics take one query per keyword, merged by offer id (`france_travail.py:195-209`). Cost: each poll makes N keyword queries of up to 7 pages each, and each query is subject to the 1,050-result ceiling described below; a query that hits it costs another 99 département queries.
5. **Region filter in plain PostgreSQL, no PostGIS.** SQL keeps offers whose département is in the region's list or whose coordinates fall inside a bounding box (radius / 111 km per degree, longitude scaled by cos(latitude)); exact haversine distance is computed in Python on the returned page (`routers/offers.py:79-101`, `167-178`). Cost: the post-filter runs per page, so `total` is only corrected for the current page and pages can come back short; `sort=distance` reorders only within a page (`routers/offers.py:144-149`, `198-199`).
6. **Schema from `create_all` at startup, no migrations.** Both processes call `init_db()` on boot (`db/engine.py:24-28`, `main.py:31`, `webapp/app.py:29-33`), so a fresh database needs no setup step. Cost: `create_all` only creates missing tables; changing a column on an existing deployment needs hand-written SQL, and there is no migration history.

## What broke and how I fixed it

The first three problems below, and the first version of the France Travail fix, were fixed in the private history before this repository's first commit, so this repository only shows the fixed state. Later fixes have their own commits.

**Railway's database URL did not match the async driver.**
Symptom: on Railway the service receives `DATABASE_URL` as `postgresql://...`, and the async engine cannot start with it. Cause: `create_async_engine` needs the async driver named in the URL, and `postgresql://` selects SQLAlchemy's default synchronous PostgreSQL driver, which is not a dependency of this project. Fix: `_async_url()` in `src/job_aggregator/db/engine.py` rewrites the prefix to `postgresql+asyncpg://` before the engine is created, so the same code accepts the explicit URL from `docker-compose`/`.env` and the one Railway injects.
The first version also turned `postgres://` into `postgres+asyncpg://`, which SQLAlchemy rejects because it has no `postgres` dialect. Fix (d296f6c): both `postgresql://` and `postgres://` now become `postgresql+asyncpg://`, and URLs that already name a driver are left unchanged. `tests/test_engine_url.py` covers both prefixes and an already-async URL; the `postgres://` case failed before the fix.

**The web process had no Railway start command bound to `$PORT`.**
Symptom: the only start commands were the Dockerfile's, which runs the aggregator (no HTTP server), and docker-compose's, which starts uvicorn on a fixed port 8080. Cause: Railway passes the port to bind in `$PORT` [TODO: link Railway docs]. Fix: a `Procfile` with two process types, `web` (uvicorn on `--port $PORT`) and `aggregator` (`python -m job_aggregator.main`).

**Templates and static files were missing from the installed package.**
Symptom: the web app works from a source checkout but not from the Docker image, which installs the package with `pip install .`. Cause: `webapp/app.py` resolves `static/` and `templates/` relative to the installed module (`_HERE`), and those directories were not declared as package data, so they were not installed. Fix: `[tool.setuptools.package-data]` in `pyproject.toml` includes `webapp/static/**/*` and `webapp/templates/**/*`.

**France Travail stops at 1,050 results per query.**
Symptom: a broad keyword search returns at most 1,050 offers; `_fetch_pages` stops paginating once the next range start reaches `API_HARD_CAP` = 1000 (`src/job_aggregator/sources/france_travail.py`). Fix, part 1: every query asks for `sort=1`, commented as newest first, so the window each poll sees is the most recent offers, and the database accumulates coverage across polls through dedup. Fix, part 2: `FranceTravailSource._fetch_all` re-runs a capped query once per département (`ALL_DEPARTMENTS`, without the `commune` filter, which the comment marks as incompatible with `departement`) and merges the results by offer id.
That second part never ran. `_fetch_all` decided a query was capped when it had at least `API_HARD_CAP + PAGE_SIZE - 1` = 1,149 results, but `_fetch_pages` returns at most 7 x 150 = 1,050, so the condition was always false. I found it by reading the code while preparing this repository, not from a production symptom. Fix (56dd589): `_fetch_pages` now returns `(results, hit_cap)`, where `hit_cap` is true only when it stopped at the cap after a full page, and `_fetch_all` branches on that flag. `tests/test_france_travail.py` drives the source with a fake search function: with endless full pages it now queries all 99 départements (it made zero département calls before the fix), and a short or empty last page triggers no sweep. [TODO: confirm the maximum range start in the current France Travail API documentation; the code assumes 1000]

### Found while preparing the public release

These were found by reading the code before publishing. Each fix that changes Python code adds a test that fails on the previous commit and passes after it; the compose change has no test.

**Seeding an empty database failed** (42d6623). `"surveillance aquatique"` appeared twice in `BNSSA_KEYWORDS` (`scripts/seed_data.py`). `_upsert_family` added both rows in one transaction, so the commit violated the `uq_family_keyword` unique constraint (`src/job_aggregator/db/models.py`) and nothing was seeded; it had presumably only ever run against a database that already had those rows. Fix: remove the duplicate and dedupe the input with `dict.fromkeys` before inserting. Tests (`tests/test_seed_data.py`): no `*_KEYWORDS` list has duplicates, and `_upsert_family` against a fake empty session adds each keyword once.

**Session cookies could be signed with an empty or public key** (01685b7). `WEBAPP_SECRET` was never checked: an empty value, or the placeholder from `.env.example`, which anyone can read once the repository is public, would still sign cookies. A cookie only carries the user's UUID, so a known key would let anyone who knows a UUID forge a session. The cookie was also not marked `Secure`. Fix: `ensure_webapp_secret()` (`src/job_aggregator/webapp/auth.py`) runs at web startup and raises if the secret is empty or the placeholder; the cookie is `Secure` unless `WEBAPP_INSECURE_COOKIES=true`, an explicit opt-out for local HTTP. Tests (`tests/test_webapp_security.py`): startup fails for an empty, blank or placeholder secret, and the login response sets `Secure` by default and drops it only with the opt-out. The aggregator and the scripts do not need the secret.

**The admin password went into shell history** (97350c0). `scripts/create_admin.py` took it as a positional argument. It now prompts twice with `getpass`; the argument form still works and prints a warning. Tests: `tests/test_create_admin.py`.

**Postgres was published on every host interface** (cf90f3e). `docker-compose.yml` used the well-known `jobbot`/`jobbot` credentials and `5432:5432`; it now binds `127.0.0.1:5432:5432`.

## Getting started

Prerequisites: Docker with Compose, and Python 3.12+ on the host for the two setup scripts (they are not copied into the image).

```bash
cp .env.example .env
# Edit .env:
#  - WEBAPP_SECRET: required. The web app will not start while it is empty or
#    still the placeholder. python -c "import secrets; print(secrets.token_urlsafe(48))"
#  - WEBAPP_INSECURE_COOKIES=true if you will open the board over plain http://
#    (session cookies are Secure by default).
#  - API keys: see the table below.

docker compose up -d postgres

python -m venv .venv && . .venv/bin/activate
pip install -e .

# The scripts run on the host, so point them at the published Postgres port.
export DATABASE_URL=postgresql+asyncpg://jobbot:jobbot@localhost:5432/jobbot
python scripts/create_admin.py admin   # prompts for a password (6+ characters)
python scripts/seed_data.py            # job families + one region per département

docker compose up --build     # postgres + aggregator (app) + web
```

Open <http://localhost:8080/login> and sign in with the admin account. `docker compose up app` or `docker compose up web` starts only the aggregator or only the web process (plus Postgres). If `WEBAPP_SECRET` is empty or still the placeholder, the `web` container exits at startup with an error naming the variable, and compose keeps restarting it until you fix `.env`; that is intended.

The compose flow above was not re-run for this release (no Docker in the environment where the fixes were made); the tests below cover the changed code paths. [TODO: re-run the compose flow end to end and remove this note]

What runs with which keys:

| Keys set | What happens |
|---|---|
| None (only `WEBAPP_SECRET`) | Postgres, the web board and the aggregator start, but no source is enabled: `RSS_FEED_URLS` is empty in `.env.example`, so nothing is ingested and the board stays empty. |
| `RSS_FEED_URLS` | RSS source. Keyless; add the feed URLs you want. |
| `NOMINATIM_USER_AGENT` | Background geocoding of offers without coordinates. No key, but Nominatim's usage policy asks for an identifying User-Agent with your contact. |
| `FRANCE_TRAVAIL_CLIENT_ID` + `FRANCE_TRAVAIL_CLIENT_SECRET` | France Travail source (register at francetravail.io and subscribe the app to the "Offres d'emploi v2" API). |
| `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` | Adzuna source. |
| `OPENAI_API_KEY` | LLM scoring. **Without it nothing is ever notified**: only scored offers are considered for alerts. |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, and/or `DISCORD_WEBHOOK_URL` | Notification channels for offers scored at or above `SCORING_THRESHOLD`. Need `OPENAI_API_KEY` to do anything. |

There is no demo data set of offers: with no source configured, the board is empty. [TODO: add a demo-offers seed so the board can be tried without any key]

## Configuration

All settings are read by `pydantic-settings` from the environment or a `.env` file (`src/job_aggregator/config.py`); variable names are the upper-case field names.

| Name | Required? | Meaning |
|---|---|---|
| `DATABASE_URL` | Yes (default targets `localhost:5432/jobbot`) | SQLAlchemy URL. `postgresql://` and `postgres://` are rewritten to `postgresql+asyncpg://`; URLs that already name a driver are used as is. |
| `WEBAPP_SECRET` | Yes for the web app | Key that signs session cookies. The web app refuses to start if it is empty or the `.env.example` placeholder. |
| `WEBAPP_INSECURE_COOKIES` | Optional, default `false` | `true` drops the `Secure` flag on the session cookie. Only for local development over plain HTTP. |
| `FRANCE_TRAVAIL_CLIENT_ID`, `FRANCE_TRAVAIL_CLIENT_SECRET` | Optional, both to enable | France Travail OAuth2 client credentials. |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Optional, both to enable | Adzuna API credentials. |
| `ADZUNA_COUNTRY` | Optional, default `fr` | Adzuna country segment in the search URL. |
| `RSS_FEED_URLS` | Optional, empty in `.env.example` | Comma-separated feed URLs; non-empty enables the RSS source. |
| `TARGET_SECTORS` | Optional | Comma-separated keywords. Pre-filter on title + description, one France Travail `motsCles` query each, and the first five joined as Adzuna `what`. Empty means no keyword filter. |
| `TARGET_LOCATION` | Optional | Substring filter on the offer location; also sent as France Travail `commune` and Adzuna `where`. |
| `TARGET_CONTRACT_TYPES` | Optional | Comma-separated France Travail contract codes (for example `CDI,CDD`); filter and `typeContrat` parameter. |
| `TARGET_SENIORITY` | Optional | Parsed into a list but not used by any filter yet. |
| `OPENAI_API_KEY` | Optional | Enables LLM scoring (and therefore notifications). |
| `SCORING_MODEL` | Optional, default `gpt-4o-mini` | Chat model used for scoring. |
| `SCORING_THRESHOLD` | Optional, default `7` | Minimum score (1-10) that triggers a notification. |
| `TARGET_PROFILE` | Optional, default `Backend Python developer, 3 years experience` | Free-text profile the LLM scores against. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Optional, both to enable | Telegram Bot API target. |
| `DISCORD_WEBHOOK_URL` | Optional | Discord webhook target. |
| `NOMINATIM_USER_AGENT` | Optional, empty in `.env.example` | Non-empty enables background geocoding; sent as the User-Agent. |
| `GEOCODE_INTERVAL` | Optional, default `10` | Minutes between geocoding runs. |
| `FETCH_FRANCE_TRAVAIL_INTERVAL` | Optional, default `120` | Minutes between France Travail polls. |
| `FETCH_RSS_INTERVAL` | Optional, default `30` | Minutes between RSS polls. |
| `FETCH_ADZUNA_INTERVAL` | Optional, default `60` | Minutes between Adzuna polls. |
| `SCORE_AND_NOTIFY_INTERVAL` | Optional, default `5` | Minutes between scoring/notification runs. |
| `WEBAPP_PORT` | Unused | Declared in settings, not read anywhere; compose uses 8080 and the `Procfile` uses `$PORT`. |
| `PORT` | Set by the platform | Port the `Procfile` `web` process binds to. |


## Deployment

The app was deployed on Railway. What the repository records:

- `Procfile` declares two process types: `web` (`python -m uvicorn job_aggregator.webapp.app:app --host 0.0.0.0 --port $PORT`) and `aggregator` (`python -m job_aggregator.main`).
- `Dockerfile` builds from `python:3.12-slim`, installs the package with `pip install .`, and its default command runs the aggregator.
- `db/engine.py` accepts the `postgresql://` URL Railway provides (see above), and `pyproject.toml` ships templates and static files inside the package.
- Both processes create missing tables on start, so a fresh Railway Postgres needs no migration step; the first admin still has to be created with `scripts/create_admin.py` against that database.
- The `web` service needs `WEBAPP_SECRET` set to a real value, or it exits at startup. Leave `WEBAPP_INSECURE_COOKIES` unset on any deployment served over HTTPS.

Which builder and start command each Railway service used is not in the repository. [TODO: document the Railway services (builder, start command, variables)]

Live: [TODO: live URL once redeployed]

## Tests

```bash
pip install -e '.[dev]'
python -m pytest
```

18 tests, all offline: no database, no network. External APIs are replaced by fakes (a fake France Travail search function, a fake SQLAlchemy session, FastAPI's `TestClient` with `init_db` stubbed).

- `tests/test_france_travail.py`: pagination and the département sweep.
- `tests/test_seed_data.py`: seed keyword lists and the keyword upsert.
- `tests/test_webapp_security.py`: startup secret check and session cookie flags.
- `tests/test_create_admin.py`: password prompt and argv fallback.
- `tests/test_engine_url.py`: `DATABASE_URL` rewriting to the asyncpg driver.

They cover the code fixes listed above, including the database URL rewrite, not the whole pipeline. There is no CI. [TODO: tests for the other pure functions: `filters/keywords.py`, `webapp/geo.py::haversine_km`, `webapp/routers/offers.py::_kw_regex`, `notifier/telegram.py::_escape_md`, the scorer's JSON parsing; and an integration test against a real Postgres]

## Status and limitations

- The deployment is currently offline. [TODO: live URL once redeployed]
- Tests cover the fixed code paths only (including the database URL rewrite); no CI, no schema migrations.
- Known bug: offer expiry is never stored. `ingest_offer` sets `expires_at` on the offer (`filters/dedup.py:41`), but `insert_if_new` builds its own insert without that column (`db/repository.py:25-41`). The column stays NULL, so the 24 h cleanup (`scheduler/jobs.py:60-78`) deletes nothing and the offers API always returns `expires_at: null`. [TODO: persist `expires_at` in `insert_if_new`]
- France Travail: the département sweep list has 99 codes and no Corsica (`2A`/`2B`). The sweep has only been exercised against a fake API.
- A France Travail offer's département is the first two characters of its postal code (`sources/france_travail.py:124`), so Corsican offers get `20` and overseas offers `97`; neither matches the seeded region codes `2A`, `2B`, `971`-`974` or `976`, so they only match those regions by coordinates. Adzuna and RSS offers have no département and match regions by coordinates only.
- Scoring throughput is 20 offers per 5 minutes with defaults; failed scorings are stored as 5 and not retried.
- An offer is marked as notified even when every channel failed; failures are recorded only in `notification_log` and the aggregator log. Notifier retries have no backoff.
- With a region filter, the total count and page sizes are approximate, and distance sorting applies within a page only.
- `TARGET_SENIORITY` is parsed but unused; `WEBAPP_PORT` is declared but unused.
- Not verified: on a first boot the aggregator and the web app both run `create_all` at the same time; concurrent `CREATE TABLE` in Postgres can fail one of them, and `restart: unless-stopped` would retry it.
- No login rate limiting and no CSRF token (the cookie is `SameSite=Lax`).
- The web UI is French only.
- [TODO: number of sources live, offers ingested per day, scoring precision, uptime, running cost]

## License

MIT. See [LICENSE](LICENSE).
