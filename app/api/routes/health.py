from fastapi import APIRouter
from app.core.config import get_settings

router = APIRouter()

@router.get("/health", tags=["health"])
def health_check() -> dict:
    """Liveness/readiness probe, Cloud run (and any container irchestrator)
    pings this to conform the app is app is before routing to it."""

    settings = get_settings()
    return{
        "status": "ok",
        "service": "egx-advisor", 
        "env": settings.app_env,
    }