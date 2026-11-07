"""SQLite by default so nobody has to stand up infra at the hackathon.

To move to Postgres/Supabase: set DATABASE_URL=postgresql+psycopg://... and pip install psycopg.
JSON columns work on both.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import settings

settings.data_dir.mkdir(parents=True, exist_ok=True)
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # normalized "brand|product"
    brand: Mapped[str | None] = mapped_column(String)
    name: Mapped[str | None] = mapped_column(String)
    dsld_id: Mapped[str | None] = mapped_column(String)
    label: Mapped[dict | None] = mapped_column(JSON)  # first confirmed label extraction
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Fingerprint(Base):
    """Running per-feature mean/variance (Welford) for one product under one protocol.

    Protocol is part of the key: if sample prep or LED timing changes, old fingerprints
    are not comparable and must not be mixed in.
    """
    __tablename__ = "fingerprints"
    product_id: Mapped[str] = mapped_column(String, primary_key=True)
    protocol: Mapped[str] = mapped_column(String, primary_key=True)
    n: Mapped[int] = mapped_column(Integer, default=0)
    mean: Mapped[dict] = mapped_column(JSON, default=dict)
    m2: Mapped[dict] = mapped_column(JSON, default=dict)
    counts: Mapped[dict] = mapped_column(JSON, default=dict)  # per-feature n (some features can be None)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)  # True if any seed scan was simulated
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Scan(Base):
    __tablename__ = "scans"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    device_id: Mapped[str | None] = mapped_column(String, index=True)
    product_id: Mapped[str | None] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|partial|complete|error
    revision: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[dict | None] = mapped_column(JSON)
    readings: Mapped[dict | None] = mapped_column(JSON)
    sample_prep: Mapped[dict | None] = mapped_column(JSON)
    features: Mapped[dict | None] = mapped_column(JSON)
    qc: Mapped[dict | None] = mapped_column(JSON)
    evidence: Mapped[dict | None] = mapped_column(JSON)
    report: Mapped[dict | None] = mapped_column(JSON)
    stages: Mapped[dict] = mapped_column(JSON, default=dict)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class CacheEntry(Base):
    __tablename__ = "cache"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict | list | None] = mapped_column(JSON)
    fetched_at: Mapped[float] = mapped_column(Float)


def init_db() -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
