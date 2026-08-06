"""
Orchestrates a full ingestion run:
1. ensure every whatchlist ticker has a stock row.
2. refresh prices for all of them (cheap, one request  do this every run)
3. refresh profiles only for stocks missing one, or older PROFILE_STALE_DAYS
(expensive-ish, one request per ticker - company descriptioin barely change)

Errors on individual tickers are collected, raised, one bad scape 
does't kill the whole run.
"""
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session 

from app.models.db_models import PriceSnapshot, Stock, utcnow
from app.models.schemas import IngestResult
from app.services import scraper, shariah
from app.services.watchlist import get_watchlist

PROFILE_TALE_DAYS= 30

def _get_or_create_stock(db: Session, ticker: str, company_name: str) -> Stock:
    stock= db.query(Stock).filter(Stock.ticker == ticker).one_or_none()
    if stock is None:
        stock = Stock(ticker = ticker, company_name=company_name)
        db.add(stock)
        db.flush()
    return stock


def run_ingestion(db: Session) -> IngestResult:
    errors: list[str] = []

    # make sure every watchlist stock exist as a row 
    watchlist = get_watchlist()
    if not watchlist:
        errors.append("could not load EGX ticker list - ingestion aborted")
        return IngestResult(prices_updated=0, profiles_updated=0, errors=errors)
    stocks_by_ticker: dict[str, Stock] = {}
    for entry in watchlist:
        stock = _get_or_create_stock(db, entry["ticker"], entry["company_name"])
        stocks_by_ticker[entry["ticker"]] = stock
    db.commit()

    prices_updated = 0
    try:
        price_data = scraper.fetch_prices([e["ticker"] for e in watchlist])
        for ticker, data in price_data.items():
            stock = stocks_by_ticker.get(ticker)
            if stock is None:
                continue
            db.add(
                PriceSnapshot(
                    stock_id= stock.id,
                    price= data["price"],
                    change_pct= data["change_pct"],
                    market_cap= data["market_cap"],
            )
        )
            prices_updated +=1 
            whatchlist_tickers = {e["ticker"] for e in watchlist}
        missing = whatchlist_tickers - set(price_data.keys())

        if missing:
            errors.append(f" No price row found for : {', '.join(sorted(missing))}")
        db.commit()
    except scraper.ScrapeError as e:
        errors.append(f"Price scape failed: {e}")

    except Exception as e: 
        errors.append(f" price scape failed unexpectedly: {e}")

    profiles_updated = 0
    stale_cutoff = utcnow() - timedelta(days=PROFILE_TALE_DAYS)
    for ticker, stock in stocks_by_ticker.items():
        needs_refresh = stock.profile_updated_at is None or stock.profile_updated_at < stale_cutoff
        if not needs_refresh:
            continue
        try:
            profile= scraper.fetch_profile(ticker)
            if profile is None:
                continue

            stock.business_description = profile["business_description"]
            stock.sector = profile["sector"]
            stock.profile_updated_at = utcnow()
            profiles_updated += 1

            try:
                shariah_result = shariah.classify_stock(stock)
                stock.shariah_status = shariah_result.status
                stock.shariah_reason = shariah_result.reason
                stock.shariah_checked_at = utcnow()
            except shariah.ShariahCheckError as e:
                errors.append(f"{ticker} shariah check failed: {e}")

        except scraper.ScrapeError as e :
            errors.append(f"{ticker} profile scrape failed: {e}")
        except Exception as e :
            errors.append(f"{ticker} profile scrape failed unexpectedly: {e}")
        time.sleep(5)
    db.commit()

    return IngestResult(prices_updated=prices_updated, profiles_updated=profiles_updated, errors=errors)
    
