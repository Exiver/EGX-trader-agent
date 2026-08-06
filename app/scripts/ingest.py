"""Manual ingestion run: python -m app.scripts.ingest"""
import logging

from app.core.database import Sessionlocal, init_db
from app.core.logging_config import configure_logging
from app.services.ingestion import run_ingestion

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    init_db()
    db = Sessionlocal()
    try:
        result = run_ingestion(db)
        logger.info(f"Prices updated: {result.prices_updated}")
        logger.info(f"Profiles updated: {result.profiles_updated}")
        if result.errors:
            logger.warning(f"{len(result.errors)} errors during run:")
            for err in result.errors:
                logger.warning(f"  - {err}")
    finally:
        db.close()


if __name__ == "__main__":
    main()