# EGX Intraday Advisor

An AI agent that analyzes live-ish Egyptian Exchange (EGX) prices and news, and
gives a daily/intraday trader a buy / hold / sell recommendation with reasoning
for each stock on their watchlist. Advisory only — it never places trades.

## Status: Phase 2 — ingestion

FastAPI app with a health check, containerized, plus a working ingestion
layer: scrapes EGX prices (stockanalysis.com) and company descriptions
(Mubasher) for a starter 30-stock watchlist, and stores them in SQLite.
No Gemini calls, no Shariah filter, no RAG yet — those come in later phases.

**Note on the scraper:** the sandbox that wrote this code could not reach
stockanalysis.com or english.mubasher.info to verify the live HTML, so
`parse_price_list_html` / `parse_profile_html` were written defensively
against a snapshot of real page content, tested against fixture HTML, but
not against the live site. Run `python -m app.scripts.ingest` first thing
and expect to debug selectors against real markup if something breaks —
that's normal for scraper code, not a sign something's fundamentally wrong.

## Project layout

```
app/
  main.py             FastAPI app entrypoint (lifespan → init_db on startup)
  core/
    config.py          Settings (env vars via pydantic-settings)
    database.py         SQLAlchemy engine/session (SQLite by default)
  api/
    routes/
      health.py          /health endpoint
      stocks.py           GET /stocks, POST /stocks/ingest
  services/
    watchlist.py        Starter watchlist: top ~30 EGX stocks by market cap
    scraper.py            Price + profile scraping (pure parse fns + fetch fns)
    ingestion.py            Orchestrates scraping → DB upsert
  models/
    db_models.py         SQLAlchemy ORM: Stock, PriceSnapshot
    schemas.py             Pydantic response schemas
  scripts/
    ingest.py             CLI: python -m app.scripts.ingest
tests/
  test_health.py
  test_scraper_parsing.py  Tests parsing logic against fixture HTML (no network)
  fixtures/
Dockerfile
docker-compose.yml
requirements.txt
requirements-dev.txt
.env.example
```

## Try the ingestion locally

```bash
python -m app.scripts.ingest
```

This scrapes prices + profiles for the watchlist and prints a summary. It
writes to `data/egx.db` (SQLite, gitignored). Then `uvicorn app.main:app --reload`
and hit `GET /stocks` to see what landed in the DB, or `POST /stocks/ingest`
to trigger the same thing over the API.

## Run locally (no Docker)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Then open http://localhost:8000/health

## Run with Docker

```bash
docker build -t egx-advisor .
docker run --rm -p 8000:8080 --env-file .env egx-advisor
```

(The container listens on port 8080 by default — that's the convention Cloud Run
expects via its `$PORT` env var. We map host port 8000 to it here just for
local convenience; Cloud Run will handle this itself at deploy time.)

Or with Docker Compose (better for local dev — supports live reload):

```bash
docker compose up --build
```

## Run tests

```bash
pytest
```

## Push to GitHub

```bash
git init
git add .
git commit -m "Phase 1: project scaffold, health check, Docker"
git branch -M main
git remote add origin https://github.com/Exiver/egx-trading-agent.git
git push -u origin main
```

(Create the empty repo on GitHub first, or use `gh repo create` if you have the GitHub CLI.)

## Roadmap

1. ✅ Scaffold — repo, Dockerfile, health check
2. ✅ Ingestion — EGX price + stock description scraper
3. Shariah compliance filter (Gemini-based)
4. News scraping + sentiment
5. RAG layer (user-uploaded files)
6. Reasoning agent (Gemini) — the actual buy/hold/sell logic
7. Streamlit UI
8. Tests + GitHub Actions CI
9. Production Dockerfile hardening
10. CI/CD to Cloud Run
11. Monitoring, rate-limit handling, polish
