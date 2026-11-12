import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .enterprise_settings import ENABLED, demo_database_url

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "app.db"
DATABASE_URL = demo_database_url() if ENABLED else os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
if DATABASE_URL == f"sqlite:///{DB_PATH}":
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
class Base(DeclarativeBase): pass

