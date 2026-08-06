"""
Csrapihnlayer, split deliberatly into:
- functions: pure functions, thml/ text in. data out. no network 
these are what the unit tests exerxise, using saved fixture html .
fetch function: di the actual HTTP call, then hands off to parse 


keeping the split matters here specifically: this sandbox that wrote this 
code cannot reach stockanalysis.com or english mubasher. info to verify the exact live markup, so the parse function 
are written defensively(matched 
against a snapshot of the real page content) but will likely need small
adjustments once you run this against the live site. when that happens,
save the failing page's html to a fixture file and we debug it together 
against real markup instead of gussing.
"""

import io
import re 

import httpx
import pandas as pd 
from bs4 import BeautifulSoup

STOCKANALYSIS_LIST_URL = "https://stockanalysis.com/list/egyptian-stock-exchange/"
MUBASHER_PROFILE_URL = "https://english.mubasher.info/markets/EGX/stocks/{ticker}/profile"
MUBASHER_NEWS_URL = "https://english.mubasher.info/markets/EGX/stocks/{ticker}/news"

HEADERS = {"User-Agent": "egx-advisor-bot/0.1 (personal project; contact: fathyelghoneimy@gmail.com)"}

class ScrapeError(Exception):
    pass

def parse_prise_list_html(html: str, tickers: list[str]) -> dict[str, dict]:
    """parse the big EGX listing table into {ticker: {price, change_pct, market_cap}},"
    "filtered down to just the tickers we care about."""

    try:
        tables = pd.read_html(io.StringIO(html), flavor="lxml")
    except ValueError as e :
        raise ScrapeError(f" No <table> found on the EGX list page site markup likely changed. {e}") from e 
    if not tables:
        raise ScrapeError("No <table> found on the EGX list page - site markup likely changed.")

    df = max(tables, key=len)
    df.columns = [str(c).strip() for c in df.columns]

    symbol_col = next((c for c in df.columns if c.lower() in ("symbol", "ticker")), None)
    price_col = next((c for c in df.columns if "price" in c.lower()), None)
    change_col = next((c for c in df.columns if "change" in c.lower()), None)
    mcap_col = next((c for c in df.columns if "market cap" in c.lower()), None)

    if not symbol_col or not price_col:
        raise ScrapeError(f" Expected symbol/ price columns, get :{list(df.columns)}")
    clean_tickers = [t["ticker"] if isinstance(t, dict) else t for t in tickers]
    wanted = set(clean_tickers)
    results: dict[str, dict] = {}
    for _, row in df.iterrows():
        symbol = str(row[symbol_col]).strip()
        if symbol not in wanted:
            continue
        try:
            price = float(str(row[price_col]).replace(",", ""))
        except (ValueError, TypeError):
            continue
        change_pct = None
        if change_col is not None:
            change_raw = str(row[change_col]).replace("%", "").strip()
            try:
                change_pct = float(change_raw)
            except ValueError:
                change_pct = None
        market_cap = str(row[mcap_col]).strip() if mcap_col is not None else None
        results[symbol] = {"price": price, "change_pct": change_pct, "market_cap": market_cap}
    return results


def fetch_prices(tickers: list[str]) -> dict[str, dict]:
    resp = httpx.get(STOCKANALYSIS_LIST_URL, headers=HEADERS, timeout=20, follow_redirects=True)
    resp.raise_for_status()
    return parse_prise_list_html(resp.text, tickers)


def parse_profile_html(html: str) -> dict:
    """
    Extract the "Company Purpose" text and sector from a Mubasher profile page.
    Uses text search rather than a fixed CSS class, since a class name is
    more likely to silently change than the "Company Purpose" heading text.
    """
    soup = BeautifulSoup(html, "lxml")
    full_text = soup.get_text(separator="\n")

    match = re.search(
    r"Company Purpose\s*\n?(.+?)(?:\n\n|\nKey (?:People|Executives)|\Z)",
    full_text,
    re.DOTALL,
)
    if not match:
        raise ScrapeError("Could not find 'Compant perpose' text - Mubasher page layout my have changed")
    description = " ".join(match.group(1).split())

    sector_match = re.search("operates within the ([A-Za-z &]+?) sector", description)
    sector = sector_match.group(1).strip() if sector_match else None

    return {"business_description": description, "sector": sector}

"""def fetch_profile(ticker: str) -> dict:
    url = MUBASHER_PROFILE_URL.format(ticker=ticker)
    resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
    resp.raise_for_status()
    return parse_profile_html(resp.text)"""
def fetch_profile(raw_ticker: str) -> dict:
    if isinstance(raw_ticker, dict):
        raw_ticker = raw_ticker.get("ticker", "")
        
    clean_t = raw_ticker.strip().replace(".CA", "")
    
    url = MUBASHER_PROFILE_URL.format(ticker=clean_t)
    
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        return parse_profile_html(resp.text)
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            print(f"⚠️ Skipped {clean_t}: Profile page not found (404).")
            return None
        raise ScrapeError(f"HTTP Error for {clean_t}: {e}") from e
        
    except httpx.RequestError as e:
        raise ScrapeError(f"Connection Error for {clean_t}: {e}") from e

    
# fetching all 223 stocks in the market 

def fetch_all_tickers() -> list[dict]:
    """ 
    Scrape the full EGX listing table and return every ticker as:
    [{"ticker": "COMI", "COMPANY_NAME": ...............}]
    same dingle request we already make for prices - no extra cost 
    """

    resp = httpx.get(STOCKANALYSIS_LIST_URL, headers=HEADERS, timeout=20, follow_redirects=True)
    resp.raise_for_status()

    try:
        tables = pd.read_html(io.StringIO(resp.text), flavor="lxml")
    except ValueError as e :
        raise ScrapeError(f"No <table> found on EGX list page: {e}") from e 

    df = max(tables, key=len)
    df.columns = [str(c).strip() for c in df.columns]

    symbol_col = next((c for c in df.columns if c.lower() in ("symbol", "ticker")), None)
    name_col = next((c for c in df.columns if "company" in c.lower() or "name" in c.lower()), None)

    if not symbol_col:
        raise ScrapeError(f"no symbol col found. got: {list(df.columns)}")

    tickers = []
    for _, row in df.iterrows():
        symbol = str(row[symbol_col]).strip()
        company_name = str(row[name_col]).strip() if name_col else symbol
        if symbol and symbol != "nan":
            tickers.append({"ticker": symbol, "company_name": company_name})
    return tickers

def parse_news_text(html: str, max_chars: int = 3000) -> str:
    """
    Extract a cleaned, bounded text blob from a Mubasher stock news page.
    Rather than parsing individual news items into a structured list (which
    needs reliable per-item boundaries this sandbox can't verify without
    live HTML), this pulls the visible text and hands the model a readable
    chunk — Gemini can parse loosely-structured text like this itself.
    """

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    lines = [line for line in lines if len(line) > 15]

    return "\n".join(lines)[:max_chars]


def fetsh_news_text(ticker: str) -> str:
    url = MUBASHER_NEWS_URL.format(ticker=ticker)
    resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
    resp.raise_for_status()
    return parse_news_text(resp.text)