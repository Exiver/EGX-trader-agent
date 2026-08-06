from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import Sessionlocal, get_db
from app.models.db_models import PriceSnapshot, Stock
from app.models.schemas import RecommendationOut, StockOut
from app.services.agent import AgentError, generate_recommendation
from app.services.scanner import scan_for_recommendations

router = APIRouter(prefix="/stocks", tags=["recommendations"])

@router.get("/{ticker}/recommendation", response_model=RecommendationOut)
def get_recommendaion(ticker: str, db:Session = Depends(get_db)):
    """
    Generates a fresh same-session recommendation on demand — one Gemini
    call per request. Deliberately not a bulk endpoint (see the note at
    the top of the build guide about free-tier quota).
    """
    try:
        return generate_recommendation(db, ticker.upper())
    except AgentError as e:
        raise HTTPException(status_code=400, detail=str(e))

def _run_scan_background():
    """Own DB session — the request-scoped one may already be closed by the time this runs."""
    db = Sessionlocal()
    try:
        scan_for_recommendations(db)
    finally:
        db.close()


@router.post("/scan")
def trigger_scan(background_tasks: BackgroundTasks):
    """
    Starts a full-market recommendation scan in the background. Likely to
    exceed daily Gemini quota before covering everything — expected.
    Check GET /stocks/buy-signals after a while to see results so far.
    """
    background_tasks.add_task(_run_scan_background)
    return {"status": "started", "message": "Scan running in background. Check /stocks/buy-signals in a while."}


@router.get("/buy-signals", response_model=list[StockOut])
def get_buy_signals(db: Session = Depends(get_db)):
    """All stocks whose most recent scan recommended BUY, sorted by confidence."""
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    stocks = db.query(Stock).filter(Stock.last_recommendation == "BUY").all()
    stocks.sort(key=lambda s: confidence_order.get(s.last_confidence, 3))

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