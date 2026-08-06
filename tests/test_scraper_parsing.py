from pathlib import Path
import pytest

from app.services.scraper import ScrapeError, parse_prise_list_html, parse_profile_html

FIXTURES = Path(__file__).parent / "fixtures"

def test_parse_price_list_html_estracts_wanted_tickers():
    html = (FIXTURES / "price_list_sample.html").read_text()
    result = parse_prise_list_html(html, tickers=["COMI", "SWDY", "NOTLISTED"])

    assert set(result.keys()) == {"COMI", "SWDY"}
    assert result["COMI"]["price"] == pytest.approx(131.85)
    assert result["COMI"]["change_pct"] == pytest.approx(-0.53)
    assert result["COMI"]["market_cap"] == "447.75B"


def test_parse_price_list_html_ignores_tickers_not_requested():
    html = (FIXTURES / "price_list_sample.html").read_text()
    result = parse_prise_list_html(html, tickers=["COMI"])
    assert "TMGH" not in result


def test_parse_price_list_html_raises_on_no_table():
    with pytest.raises(ScrapeError):
        parse_prise_list_html("<html><body>no table here</body></html>", tickers=["COMI"])


def test_parse_profile_html_extracts_description_and_sector():
    html = (FIXTURES / "mubasher_profile_sample.html").read_text()
    result = parse_profile_html(html)

    assert "Egyptian Resorts" in result["business_description"]
    assert result["sector"] == "Consumer Services"


def test_parse_profile_html_raises_when_purpose_missing():
    with pytest.raises(ScrapeError):
        parse_profile_html("<html><body>nothing relevant here</body></html>")