from datetime import datetime

from app.models.db_models import PriceSnapshot, Stock
from app.services.agent import _build_prompt


def _make_stock(**overrides) -> Stock:
    stock = Stock(
        ticker="TEST",
        company_name="Test Company",
        sector="Technology",
        business_description="A test company that makes test products.",
    )
    for key, value in overrides.items():
        setattr(stock, key, value)
    return stock

def _make_snapshot(price: float, change_pct: float | None, fetched_at: datetime) -> PriceSnapshot:
    snap = PriceSnapshot(price= price, change_pct=change_pct, market_cap= "1.0B")
    snap.fetched_at = fetched_at
    return snap


def test_build_prompt_includes_stock_identity():
    stock = _make_stock()
    history = [_make_snapshot(100.0, 1.5, datetime(2026, 8, 5, 10, 0))]
    prompt = _build_prompt(stock, history, news_text="" , rag_chunks=[])

    assert "TEST" in prompt
    assert "Test Company" in prompt
    assert "Technology" in prompt

def test_build_prompt_includes_price_history():
    stock = _make_stock()
    history = [_make_snapshot(100.0, 1.5, datetime(2026, 8, 5, 10, 0))]
    prompt = _build_prompt(stock, history, news_text="", rag_chunks=[])

    assert "100.0" in prompt
    assert "+1.50%" in prompt

def test_build_includes_empty_news_and_rag():
    stock = _make_stock()
    history = [_make_snapshot(100.0, 1.5, datetime(2026, 8, 5, 10, 0))]
    prompt = _build_prompt(stock, history, news_text="", rag_chunks=[])

    assert "No recent news found" in prompt
    assert "No user-provided notes relevant" in prompt

def test_build_prompt_includes_news_and_rag():
    stock = _make_stock()
    history = [_make_snapshot(100.0, 1.5, datetime(2026, 8, 5, 10, 0))]
    prompt = _build_prompt(
        stock, history,
          news_text="Company announces record profits.",
            rag_chunks=["Trader is cautious on this sector."])


    assert "Company announces record profits." in prompt
    assert "Trader is cautious on this sector." in prompt
    