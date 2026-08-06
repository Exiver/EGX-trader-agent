"""
Dynamic watchlist - fetches all tickers currently listed on EGX from '
stockanalysis.com at the start of each esession ingestion run. No hardcoded list 
to mintain. falls back to empty list with an error log if the fetch 
fails so the rest of the ingestion run can still proceed.
"""
import logging
logger = logging.getLogger(__name__)
from app.services.scraper import ScrapeError, fetch_all_tickers
def get_watchlist() -> list[dict]:
    """
    Returns the full EGX listing as :
    [{"ticker": "COMI", "company_name": "..."}, ...]

    Called once per ingestion run — not cached, so it always reflects
    the current market listing (new listings, delistings, suspensions).
    """
    try:
        watchlist= fetch_all_tickers()
        logger.info(f"watchlist loaded: {len(watchlist)} tickers from EGX listing")
        return watchlist
    except ScrapeError as e :
        logger.error(f"Failed to fetch EGX ticker list: {e}")
        return []
    