"""
Manual ingestion run: python -m app.scripts.ingest

Useful for testing the scraper directly (with real error tracebacks) without
going through the API, and for later plugging into a cron job / scheduler."""

from app.core.database import Sessionlocal, init_db
from app.services.ingestion import run_ingestion
def main() -> None:
    init_db()                                    
    db = Sessionlocal()
    try:
        result = run_ingestion(db)
        print(f"price updated: {result.prices_updated}")
        print(f"prefiles updated: {result.profiles_updated}")
        if result.errors:
            print("Errors: ")
            for err in result.errors:
                print(f"  - {err}")

    finally:
        db.close()


if __name__=="__main__":
    main()