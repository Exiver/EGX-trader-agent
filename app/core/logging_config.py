"""
Centralized logging setup. configure_logging() is called once, early —
main.py does this at import time for the API, and the CLI script
(ingest.py) calls it explicitly since it doesn't go through main.py's
import chain.
"""
import logging

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )