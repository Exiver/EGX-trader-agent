from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import PriceSnapshot, Stock, utcnow
from app.models.schemas import IngestResult, StockOut
from app.services import shariah
from app.services.ingestion import run_ingestion

router = APIRouter(prefix="/stocks", tags=["stocks"])

@router.get("", response_model=list[StockOut])
def list_stocks(shariah: str | None = None, db: Session = Depends(get_db)):
    """
    GET /stocks — all stocks.
    GET /stocks?shariah=compliant — only Shariah-compliant stocks.
    GET /stocks?shariah=non_compliant / ?shariah=unclear also work.
    """
    query = db.query(Stock)
    if shariah:
        query = query.filter(Stock.shariah_status == shariah)
    stocks = query.order_by(Stock.ticker).all()

    out = []
    for stock in stocks:
        latest = (
            db.query(PriceSnapshot)
            .filter(PriceSnapshot.stock_id == stock.id)
            .order_by(PriceSnapshot.fetched_at.desc())
            .first()
        )
        item = StockOut.model_validate(stock)
        if latest:
            item.latest_price = latest
        out.append(item)
    return out
@router.post("/ingest", response_model=IngestResult)
def trigger_ingestion(db: Session = Depends(get_db)):
    """
    Manually trigger a refresh, fine for now - phase 10 (CI/CD) adds a 
    scheduled job so this runs automaticlly during EGX traiding hours 
    insted of needing a manual hit."""

    return run_ingestion(db)

@router.post("/{ticker}/shariah-check", response_model=StockOut)
def recheck_shariah(ticker: str, db: Session = Depends(get_db)):
    """Force a fresh Shariah classification for one ticker, right now."""
    stock = db.query(Stock).filter(Stock.ticker == ticker.upper()).one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found.")

    try:
        result = shariah.classify_stock(stock)
        stock.shariah_status = result.status
        stock.shariah_reason = result.reason
        stock.shariah_checked_at = utcnow()
        db.commit()
        db.refresh(stock)
    except shariah.ShariahCheckError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return stock