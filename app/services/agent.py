"""
Reasoning agent: turns price history + company description into a
same-session buy/hold/sell call using Gemini. Generated on demand, one
ticker at a time — see the note at the top of this guide about why this
isn't a batch job.

Price-action-only for now. No news sentiment wired in yet (Phase 4).
Every recommendation is explicitly caveated for that reason, both in the
prompt (so the model doesn't overstate confidence) and in the response
(so the trader sees the limitation, not just the verdict).
"""

from datetime import datetime, timezone
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.db_models import PriceSnapshot, Stock
from app.models.schemas import RecommendationOut
from app.services import scraper, rag

MODEL_NAME = "gemini-3.5-flash"

class RecommendatioLLMOutput(BaseModel):
    """ what we ask gemini to return - separate from RecommendationLLMOurput,
    which is what out api returns (that one adds tickers, price, disclamer,
    etc, that gemini never sees or generate)."""
    recommendation: Literal["BUY", "HOLD", "SELL"]
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    reasoning: str


class AgentError(Exception):
    pass


def _get_client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise AgentError("GENAI API_KEY  is not set - check your .env file ")
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

def generate_recommendation(db: Session, ticker: str) -> RecommendationOut:
    stock = db.query(Stock).filter(Stock.ticker == ticker).one_or_none()
    if stock is None:
        raise AgentError(f" Ticker '{ticker}' not found - check the symbols or run injestion first.")
    history = (
        db.query(PriceSnapshot)
        .filter(PriceSnapshot.stock_id == stock.id)
        .order_by(PriceSnapshot.fetched_at.desc())
        .limit(10)
        .all()
    )
    history = list(reversed(history))

    if not history:
        raise AgentError(f" No price data for '{ticker}' yet - run ingestion first")
    latest = history[-1]

    try:
        news_text = scraper.fetsh_news_text(ticker=ticker)

    except Exception:
        news_text = ""
    try:
        rag_query = f"{stock.ticker} {stock.company_name} {stock.sector or ''}"
        rag_chunks = rag.retrieve_relevant_chunks(db, rag_query, top_k=3)
    except rag.RagError:
        rag_chunks = []

    client = _get_client()
    prompt = _build_prompt(stock=stock, history=history, news_text=news_text, rag_chunks=rag_chunks)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RecommendatioLLMOutput,
            ),
        )

    except Exception as e :
        raise AgentError(f"Gemini request failed: {e}") from e

    parsed: RecommendatioLLMOutput | None = response.parsed
    if parsed is None :
        raise AgentError(f"Gemini didn't return valid structured output")

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
