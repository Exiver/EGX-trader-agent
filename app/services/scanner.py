"""
Batch recommendation scan. Runs generate_batch_recommendations() (with RAG
skipped) across chunks of the market, storing the result on each Stock 
row as it completes. This avoids hitting strict daily API quotas.
"""
import logging
import time

from sqlalchemy.orm import Session

from app.models.db_models import Stock, utcnow
from app.services.agent import AgentError, generate_batch_recommendations

logger = logging.getLogger(__name__)

def scan_for_recommendations(db: Session, batch_size: int = 10) -> dict:
    stocks = db.query(Stock).all()
    succeeded = 0
    failed = 0

    # Process stocks in chunks of 'batch_size'
    for i in range(0, len(stocks), batch_size):
        batch = stocks[i:i + batch_size]
        tickers = [stock.ticker for stock in batch]
        
        logger.info(f"Processing batch {i // batch_size + 1}: {tickers}")
        
        try:
            # Pass the list of tickers to the agent. 
            # Expecting a dictionary returned: { "COMI": rec_obj, "SWDY": rec_obj, ... }
            batch_recs = generate_batch_recommendations(db, tickers, skip_rag=True)
            
            for stock in batch:
                if stock.ticker in batch_recs:
                    rec = batch_recs[stock.ticker]
                    stock.last_recommendation = rec.recommendation
                    stock.last_confidence = rec.confidence
                    stock.last_recommendation_reason = rec.reasoning
                    stock.last_recommendation_at = utcnow()
                    succeeded += 1
                    logger.info(f"{stock.ticker}: {rec.recommendation} ({rec.confidence})")
                else:
                    failed += 1
                    logger.warning(f"{stock.ticker} was missing from the batch API response.")
            
            # Commit the entire batch at once
            db.commit()
            
        except AgentError as e:
            failed += len(batch)
            logger.warning(f"Batch {i // batch_size + 1} failed: {e}")
        except Exception as e:  # noqa: BLE001
            failed += len(batch)
            logger.error(f"Batch {i // batch_size + 1} failed unexpectedly: {e}")
        
        # Keep a small delay to avoid hitting Requests-Per-Minute (RPM) limits
        time.sleep(4)

    logger.info(f"Scan complete: {succeeded} succeeded, {failed} failed")
    return {"succeeded": succeeded, "failed": failed}