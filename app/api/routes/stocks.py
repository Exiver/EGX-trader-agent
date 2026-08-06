from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import get_db, Sessionlocal
from app.models.db_models import PriceSnapshot, Stock, utcnow
from app.models.schemas import StockOut
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

@router.post("/ingest")
def trigger_ingestion(background_tasks: BackgroundTasks):
    """
    Starts ingestion in the background and returns immediately — a
    synchronous scrape of ~220 tickers takes several minutes, long enough
    that Render's proxy (and likely other platforms') kills the connection
    before it finishes. Check GET /stocks after a few minutes to see
    results land.
    """
    background_tasks.add_task(_run_ingestion_background)
    return {"status": "started", "message": "Ingestion running in the background. Check /stocks in a few minutes."}

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

def _run_ingestion_background():
    """
    Runs in the background, after the HTTP response has already been sent.
    Uses its own fresh DB session rather than the request's — the
    request-scoped session from Depends(get_db) may already be closed by
    the time this actually executes.
    """
    db = Sessionlocal()
    try:
        run_ingestion(db)
    finally:
        db.close()


