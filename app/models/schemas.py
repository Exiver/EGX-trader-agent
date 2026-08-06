from datetime import datetime

from pydantic import BaseModel

class PriceSnapshotOut(BaseModel):
    price: float
    change_pct: float | None
    market_cap: str | None
    fetched_at: datetime

    model_config = {"from_attributes": True}


class StockOut(BaseModel):
    ticker: str
    company_name: str
    sector: str | None
    business_description: str | None
    shariah_status: str | None
    shariah_reason: str | None
    last_recommendation: str | None = None
    last_confidence: str | None = None
    last_recommendation_reason: str | None = None
    latest_price: PriceSnapshotOut | None = None

    model_config = {"from_attributes": True}

class IngestResult(BaseModel):
    prices_updated: int
    profiles_updated: int 
    errors: list[str]


class RecommendationOut(BaseModel):
    ticker: str
    company_name: str
    recommendation: str 
    confidence: str
    reasoning: str
    latest_price: float
    change_pct: float | None
    generated_at: datetime
    disclaimer: str = (
        "Advisory only, not investment advivce. price-action only-"
            )
    

    