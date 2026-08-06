"""
Batch recommendation scan. Runs generate_recommendation() (with RAG
skipped, to roughly halve Gemini usage) across every stock with price
data, storing the result on each Stock row as it completes.

WILL likely exceed Gemini's free-tier daily quota before covering the
full watchlist on a ~220-stock market — expected, not a bug. Whatever
succeeds before quota runs out gets stored; stocks that fail (quota or
otherwise) simply keep whatever result they had from a previous scan (or
None, if never scanned). Rerun after quota resets to fill in more.
"""
import logging

from sqlalchemy.orm import Session

from app.models.db_models import Stock, utcnow
from app.services.agent import AgentError, generate_recommendation

logger = logging.getLogger(__name__)


def scan_for_recommendations(db: Session) -> dict:
    stocks = db.query(Stock).all()
    succeeded = 0
    failed = 0

    for stock in stocks:
        try:
            rec = generate_recommendation(db, stock.ticker, skip_rag=True)
            stock.last_recommendation = rec.recommendation
            stock.last_confidence = rec.confidence
            stock.last_recommendation_reason = rec.reasoning
            stock.last_recommendation_at = utcnow()
            db.commit()
            succeeded += 1
            logger.info(f"{stock.ticker}: {rec.recommendation} ({rec.confidence})")
        except AgentError as e:
            failed += 1
            logger.warning(f"{stock.ticker} recommendation failed: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.error(f"{stock.ticker} recommendation failed unexpectedly: {e}")

    logger.info(f"Scan complete: {succeeded} succeeded, {failed} failed")
    return {"succeeded": succeeded, "failed": failed}