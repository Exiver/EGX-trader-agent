"""
Database setup. Defaults to a local SQLite file so Phase 2 works with zero
external services. Swap to Postgres later just by setting DATABASE_URL —
nothing else in the app needs to change.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

settings = get_settings()

default_sqllite_url = "sqlite:///./data/egx.db"
db_url = settings.database_url or default_sqllite_url
connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
engine = create_engine(db_url, connect_args=connect_args)
Sessionlocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    """ Fastapi dependancy - yield a session and always closes it"""
    db = Sessionlocal()
    try:
        yield db
    finally:
        db.close()


def init_db()-> None:
    """Create tables that don't exsit yet. call once on startup"""
    import os 

    if db_url.startswith("sqlite:///./"):
        os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)