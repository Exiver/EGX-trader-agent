# EGX Intraday Advisor

An AI agent that analyzes live EGX (Egyptian Exchange) prices and news, and
gives a daily/intraday trader a same-session buy / hold / sell recommendation
with reasoning for stocks on the market. Advisory only — it never places
trades. Includes a Shariah compliance screen, a RAG layer for the trader's
own notes, and a batch scanner that surfaces BUY signals across the market.

**Live:** the API is deployed on Render, backed by Neon Postgres, scraping
the full EGX-listed market (~220 tickers) dynamically. See **Known issues**
below for the current state of the UI deployment.

## Status: Core roadmap complete (Phases 1–11) + batch BUY scan

## What it does

- Scrapes live EGX prices (stockanalysis.com) and company profiles/news
  (Mubasher) for every currently-listed stock — not a fixed list, refreshed
  dynamically each ingestion run.
- Screens each stock for Shariah compliance via Gemini, using standard
  industry-based screening criteria (a business-activity screen, not a full
  financial-ratio screen — see the caveat in `app/services/shariah.py`).
- Generates a same-session BUY / HOLD / SELL recommendation for any ticker
  on demand, reasoning over live price action, recent news, and the
  trader's own uploaded notes (RAG) together in one Gemini call.
- Lets the trader upload `.txt`/`.md` notes (strategy rules, market context,
  anything) that get chunked, embedded, and automatically pulled into future
  recommendations when relevant.
- Runs a full-market batch scan that stores a recommendation for every
  stock and surfaces just the current BUY signals, sorted by confidence.
- A Shariah-compliant filter on the main stock list.
- Streamlit dashboard for all of the above.

## Project layout

```
app/
  main.py                  FastAPI entrypoint — lifespan → init_db, logging setup, all routers
  core/
    config.py                Settings (env vars via pydantic-settings)
    database.py                SQLAlchemy engine/session (SQLite locally, Postgres in prod via DATABASE_URL)
    logging_config.py            Structured logging setup (Phase 11)
    retry.py                       Rate-limit-aware retry wrapper for Gemini calls (Phase 11)
  api/
    routes/
      health.py                 /health
      stocks.py                   GET /stocks (optional ?shariah= filter), POST /stocks/ingest (background),
                                     POST /stocks/{ticker}/shariah-check
      recommendations.py            GET /stocks/{ticker}/recommendation, POST /stocks/scan (background),
                                       GET /stocks/buy-signals
      rag.py                          POST /rag/upload, GET /rag/documents, DELETE /rag/documents/{filename}
  services/
    watchlist.py              Dynamically fetches the full current EGX listing (not a static list)
    scraper.py                  Prices, company profiles, and news scraping (stockanalysis.com + Mubasher)
    ingestion.py                  Orchestrates scraping → DB, triggers Shariah classification on profile refresh
    shariah.py                      Gemini-based Shariah compliance classification
    agent.py                          Same-session recommendation reasoning (price + news + RAG → Gemini)
    rag.py                              Chunking, embedding, and retrieval for uploaded notes
    scanner.py                           Full-market batch recommendation scan (paced to respect rate limits)
  models/
    db_models.py               SQLAlchemy ORM: Stock, PriceSnapshot, RagChunk
    schemas.py                   Pydantic response schemas
  scripts/
    ingest.py                  CLI: python -m app.scripts.ingest
tests/
  test_health.py
  test_scraper_parsing.py     Scraper parsing logic against fixture HTML (no network)
  test_agent_prompt.py         Prompt-building logic (no network)
  test_rag_chunking.py          Chunking + cosine similarity (no network)
  fixtures/
Dockerfile                  API image
Dockerfile.streamlit          UI image
docker-compose.yml             Both services wired together for local dev
render.yaml                      Render Blueprint — defines both services as code
requirements.txt                   API dependencies
requirements-streamlit.txt           UI-only dependencies (kept slim — no pandas/sqlalchemy/etc.)
requirements-dev.txt                   Test-only dependencies
streamlit_app.py                         Dashboard — talks to the API over HTTP, not a direct import
.env.example
.github/workflows/ci.yml                   Tests on every push/PR
```

## Environment variables

Copy `.env.example` to `.env` and fill in:

```txt
APP_ENV=local
LOG_LEVEL=info

GEMINI_API_KEY=       # from aistudio.google.com/app/apikey
DATABASE_URL=         # blank = local SQLite (data/egx.db). Set to a Postgres URL (e.g. Neon) for production.
```

## Run locally (no Docker)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env             # then fill in GEMINI_API_KEY
uvicorn app.main:app --reload
```

Then, in a separate terminal, run the UI:

```bash
pip install -r requirements-streamlit.txt
streamlit run streamlit_app.py
```

Try the ingestion directly (useful for debugging without going through the API):

```bash
python -m app.scripts.ingest
```

## Run with Docker Compose (both services)

```bash
docker compose up --build
```

API at `http://localhost:8000`, UI at `http://localhost:8501`. The UI talks
to the API over Docker's internal network (`BACKEND_URL=http://api:8080`),
not `localhost`.

## Run tests

```bash
pytest -v
```

Every test runs without network access or a real Gemini key — pure-function
tests against fixture HTML and constructed objects. `google-genai` calls
themselves aren't covered by automated tests (a known gap, not a silent
omission — see the note in the Phase 8 build notes).

## Deployment

Deployed on [Render](https://render.com) via `render.yaml` (a Blueprint —
both services defined as code, committed to the repo). Auto-deploys on every
push to `main`. Database is [Neon](https://neon.tech) Postgres — permanent
free tier, no card required.

Free-tier trade-off, worth knowing: Render's free services spin down after
15 minutes idle; the next request takes 30-50 seconds to wake back up.

`POST /stocks/ingest` and `POST /stocks/scan` both run as **background
tasks**, returning immediately rather than blocking the HTTP response —
necessary because both operations take several minutes to hours, and
Render's proxy (like most platforms') kills long-held connections with a
502. Check `GET /stocks` or `GET /stocks/buy-signals` after a while to see
results land.

## Gemini rate limits — read this before running a full-market scan

`gemini-3.5-flash`'s free tier caps at **20 requests/minute** (confirmed
from the actual `429` error body, not the docs). `app/core/retry.py` retries
rate-limited calls with exponential backoff, and `scanner.py` paces requests
at ~3.5s apart to stay under that ceiling proactively rather than sprinting
into 429s and eating expensive backoff cycles. Even paced, a full ~220-stock
scan takes a long time and may span multiple runs if the daily quota is hit
— that's expected. Results are stored incrementally, so nothing is lost
between runs; just rerun `POST /stocks/scan` later to fill in more.

## Known issues

- **Streamlit segfaults specifically on Render's free tier.** Works fine
  locally and in Docker Compose — this is a Render-hosting resource/
  compatibility issue (likely the 512MB memory ceiling colliding with
  Streamlit's dependency footprint: pyarrow, pandas via pydeck, altair,
  pillow, protobuf all load at startup). Workaround: run the UI locally
  pointed at the live API:
  ```bash
  # PowerShell
  $env:BACKEND_URL = "https://egx-advisor-api.onrender.com"
  streamlit run streamlit_app.py
  ```
  Real fix, not yet done: move the UI to Streamlit Community Cloud, which is
  free hosting tuned specifically for this dependency footprint.

## Roadmap

1. ✅ Scaffold — repo, Dockerfile, health check
2. ✅ Ingestion — dynamic full-market EGX price + profile scraper
3. ✅ Shariah compliance filter (Gemini-based, business-activity screen)
4. ✅ News — folded directly into the recommendation agent's prompt (not a separate stored step)
5. ✅ RAG layer — user-uploaded notes, chunked/embedded/retrieved
6. ✅ Reasoning agent (Gemini) — same-session buy/hold/sell, on-demand per ticker
7. ✅ Streamlit UI (works locally/Compose; Render UI hosting is a known open issue)
8. ✅ Tests + GitHub Actions CI
9. ✅ Production Dockerfiles — two hardened, non-root images
10. ✅ CI/CD — deployed to Render (switched from the original Cloud Run plan for setup simplicity), Neon Postgres
11. ✅ Rate-limit retry handling + structured logging
12. ✅ Full-market BUY-signal batch scan, paced for Gemini's rate limits

## Disclaimer

Advisory only. Not investment advice. Scraped data has inherent lag; Gemini's
read of news/sentiment is a signal, not a fact. The Shariah screen is a
business-activity classification, not a scholarly ruling — treat "unclear"
results as needing further review, not as compliant by default.