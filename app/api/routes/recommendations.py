from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas import RecommendationOut
from app.services.agent import AgentError, generate_recommendation

router = APIRouter(prefix="/stocks", tags=["recommendation"])

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