from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.routes import health, recommendations, stocks, rag
from app.core.database import init_db
from app.core.logging_config import configure_logging

configure_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title= "EGX Intraday Advisor",
    description="Advisory only agent for daily EGX traders. not investment advice.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(stocks.router)
app.include_router(recommendations.router)
app.include_router(rag.router)

@app.get("/", tags=["root"])
def root()-> dict:
    return {"message": "EGX intraday advisor API - see / docs for endpoints."}