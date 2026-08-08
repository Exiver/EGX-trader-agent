"""
Reasoning agent: turns price history + company description into a
same-session buy/hold/sell call using Gemini. Generated on demand, either
one ticker at a time or in batches to optimize API quota usage.

Price-action-only for now. No news sentiment wired in yet (Phase 4).
Every recommendation is explicitly caveated for that reason, both in the
prompt (so the model doesn't overstate confidence) and in the response
(so the trader sees the limitation, not just the verdict).
"""

from datetime import datetime, timezone
import logging
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.db_models import PriceSnapshot, Stock
from app.models.schemas import RecommendationOut
from app.services import scraper, rag
from app.core.retry import call_with_retry

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-3.5-flash-lite"

class RecommendatioLLMOutput(BaseModel):
    """What we ask Gemini to return for single-ticker requests."""
    recommendation: Literal["BUY", "HOLD", "SELL"]
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    reasoning: str


# --- Models for Batch Outputs ---
class StockRecommendationItem(BaseModel):
    ticker: str
    recommendation: Literal["BUY", "HOLD", "SELL"]
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    reasoning: str


class BatchLLMOutput(BaseModel):
    """Schema enforcing structured list responses for batch generation."""
    recommendations: list[StockRecommendationItem]


class AgentError(Exception):
    pass


def _get_client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise AgentError("GENAI API_KEY is not set - check your .env file")
    return genai.Client(api_key=settings.gemini_api_key)


def _build_prompt(stock: Stock, history: list[PriceSnapshot], news_text: str, rag_chunks: list[str]) -> str:
    history_lines = "\n".join(
        f"  {snap.fetched_at.isoformat()}: {snap.price} EGP "
        f"({snap.change_pct:+.2f}% on day)"
        if snap.change_pct is not None
        else f"  {snap.fetched_at.isoformat()}: {snap.price} EGP"
        for snap in history
    )
    description = (stock.business_description or "No description available.")[:800]
    news_section = news_text.strip() if news_text.strip() else "No recent news found for this stock."
    rag_section = "\n\n".join(rag_chunks) if rag_chunks else "No user-provided notes relevant to this stock."

    return f"""
You are an intraday trading advisor for the Egyptian Exchange (EGX). The
trader you're advising buys and sells within the SAME trading session — no
overnight holds. Give a same-session call: buy now and plan to exit by end
of session, hold off, or sell if already held.

You have price data, recent news, and the trader's own notes below — no
technical indicators or financial statements beyond what's in the
description. Reflect any real limitation honestly in your reasoning.

Stock: {stock.ticker} — {stock.company_name}
Sector: {stock.sector or "unknown"}
Business description: {description}

Recent price history (most recent last):
{history_lines or "  No price history available."}

Recent news (scraped page text, may include some site navigation noise):
{news_section}

Trader's own notes/context (uploaded by the trader, may or may not be
relevant to this specific stock — use your judgment):
{rag_section}

Respond with a same-session recommendation (BUY, HOLD, or SELL), a
confidence level (low, medium, or high), and 2-4 sentences of reasoning
that references the price action, news, and notes above where genuinely
relevant. Don't force a connection to the notes section if it isn't
actually relevant to this stock — say so instead.
""".strip()


def _build_batch_prompt(stocks_data: list[dict]) -> str:
    """Combines structured data payload for multiple stocks into one batch prompt."""
    formatted_payload = ""

    for item in stocks_data:
        stock: Stock = item["stock"]
        history: list[PriceSnapshot] = item["history"]
        news_text: str = item["news_text"]
        rag_chunks: list[str] = item["rag_chunks"]

        history_lines = "\n".join(
            f"  {snap.fetched_at.isoformat()}: {snap.price} EGP "
            f"({snap.change_pct:+.2f}% on day)"
            if snap.change_pct is not None
            else f"  {snap.fetched_at.isoformat()}: {snap.price} EGP"
            for snap in history
        )
        description = (stock.business_description or "No description available.")[:500]
        news_section = news_text.strip() if news_text.strip() else "No recent news found."
        rag_section = "\n\n".join(rag_chunks) if rag_chunks else "None."

        formatted_payload += f"""
=== STOCK TICKER: {stock.ticker} ===
Company: {stock.company_name}
Sector: {stock.sector or "unknown"}
Description: {description}

Price History:
{history_lines or "  No price history."}

News:
{news_section}

Trader Notes:
{rag_section}
------------------------------------
"""

    return f"""
You are an intraday trading advisor for the Egyptian Exchange (EGX).
The trader buys and sells within the SAME trading session — no overnight holds.

Evaluate the following batch of stocks and provide a same-session call (BUY, HOLD, or SELL), 
a confidence level (LOW, MEDIUM, or HIGH), and concise 2-3 sentence reasoning for EVERY stock listed below.

STOCKS DATA:
{formatted_payload}

Ensure every stock ticker present in the request is included in your structured JSON response array.
""".strip()


def generate_recommendation(db: Session, ticker: str, skip_rag: bool = False) -> RecommendationOut:
    stock = db.query(Stock).filter(Stock.ticker == ticker).one_or_none()
    if stock is None:
        raise AgentError(f"Ticker '{ticker}' not found - check the symbols or run ingestion first.")
    
    history = (
        db.query(PriceSnapshot)
        .filter(PriceSnapshot.stock_id == stock.id)
        .order_by(PriceSnapshot.fetched_at.desc())
        .limit(10)
        .all()
    )
    history = list(reversed(history))

    if not history:
        raise AgentError(f"No price data for '{ticker}' yet - run ingestion first")
    latest = history[-1]

    try:
        news_text = scraper.fetsh_news_text(ticker=ticker)
    except Exception:
        news_text = ""

    if skip_rag:
        rag_chunks = []
    else:
        try:
            rag_query = f"{stock.ticker} {stock.company_name} {stock.sector or ''}"
            rag_chunks = rag.retrieve_relevant_chunks(db, rag_query, top_k=3)
        except rag.RagError:
            rag_chunks = []

    client = _get_client()
    prompt = _build_prompt(stock=stock, history=history, news_text=news_text, rag_chunks=rag_chunks)

    try:
        response = call_with_retry(
            client.models.generate_content,
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RecommendatioLLMOutput,
            ),
        )
    except Exception as e:
        raise AgentError(f"Gemini request failed: {e}") from e

    parsed: RecommendatioLLMOutput | None = response.parsed
    if parsed is None:
        raise AgentError("Gemini didn't return valid structured output")

    return RecommendationOut(
        ticker=stock.ticker,
        company_name=stock.company_name,
        recommendation=parsed.recommendation,
        confidence=parsed.confidence,
        reasoning=parsed.reasoning,
        latest_price=latest.price,
        change_pct=latest.change_pct,
        generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )


def generate_batch_recommendations(
    db: Session, tickers: list[str], skip_rag: bool = True
) -> dict[str, RecommendationOut]:
    """
    Fetches context for multiple tickers and queries Gemini in a single batch request.
    Returns a mapping of ticker -> RecommendationOut objects.
    """
    if not tickers:
        return {}

    stocks_data = []
    latest_snapshots = {}

    # 1. Fetch data for all requested tickers
    for ticker in tickers:
        stock = db.query(Stock).filter(Stock.ticker == ticker).one_or_none()
        if not stock:
            logger.warning(f"Batch generation skipped unknown ticker: {ticker}")
            continue

        history = (
            db.query(PriceSnapshot)
            .filter(PriceSnapshot.stock_id == stock.id)
            .order_by(PriceSnapshot.fetched_at.desc())
            .limit(10)
            .all()
        )
        if not history:
            logger.warning(f"Batch generation skipped ticker without price history: {ticker}")
            continue

        history = list(reversed(history))
        latest_snapshots[ticker] = history[-1]

        try:
            news_text = scraper.fetsh_news_text(ticker=ticker)
        except Exception:
            news_text = ""

        rag_chunks = []
        if not skip_rag:
            try:
                rag_query = f"{stock.ticker} {stock.company_name} {stock.sector or ''}"
                rag_chunks = rag.retrieve_relevant_chunks(db, rag_query, top_k=2)
            except rag.RagError:
                rag_chunks = []

        stocks_data.append({
            "stock": stock,
            "history": history,
            "news_text": news_text,
            "rag_chunks": rag_chunks,
        })

    if not stocks_data:
        raise AgentError("No valid stock data found for any ticker in the requested batch.")

    # 2. Build prompt and invoke Gemini API
    client = _get_client()
    prompt = _build_batch_prompt(stocks_data)

    try:
        response = call_with_retry(
            client.models.generate_content,
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BatchLLMOutput,
            ),
        )
    except Exception as e:
        raise AgentError(f"Gemini batch request failed: {e}") from e

    parsed: BatchLLMOutput | None = response.parsed
    if parsed is None or not parsed.recommendations:
        raise AgentError("Gemini failed to return structured output for batch recommendations.")

    # 3. Construct dictionary mapping ticker -> RecommendationOut
    results: dict[str, RecommendationOut] = {}
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for item in parsed.recommendations:
        ticker = item.ticker
        if ticker in latest_snapshots:
            stock_obj = next(s["stock"] for s in stocks_data if s["stock"].ticker == ticker)
            latest = latest_snapshots[ticker]

            results[ticker] = RecommendationOut(
                ticker=stock_obj.ticker,
                company_name=stock_obj.company_name,
                recommendation=item.recommendation,
                confidence=item.confidence,
                reasoning=item.reasoning,
                latest_price=latest.price,
                change_pct=latest.change_pct,
                generated_at=now,
            )

    return results