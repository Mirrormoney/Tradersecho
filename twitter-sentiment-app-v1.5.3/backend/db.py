
from sqlalchemy import (create_engine, Integer, String, Boolean, DateTime, Float,
                        select, Index, UniqueConstraint, func)
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
import os

# Ensure .env in backend/ is loaded
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
DB_URL = os.getenv("DB_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/sentiment")

engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    pro: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

class MentionMinute(Base):
    __tablename__ = "mention_minutes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    mentions: Mapped[int] = mapped_column(Integer, default=0)
    pos: Mapped[int] = mapped_column(Integer, default=0)
    neg: Mapped[int] = mapped_column(Integer, default=0)
    neu: Mapped[int] = mapped_column(Integer, default=0)
    # New fields for adapters/dedup
    source: Mapped[str] = mapped_column(String(32), default="twitter", index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_mm_ticker_ts", "ticker", "ts"),
        UniqueConstraint("source", "external_id", name="uq_mm_source_external"),
    )

class DailyRollup(Base):
    __tablename__ = "daily_rollups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    day: Mapped[datetime] = mapped_column(DateTime, index=True)
    mentions: Mapped[int] = mapped_column(Integer, default=0)
    pos: Mapped[int] = mapped_column(Integer, default=0)
    neg: Mapped[int] = mapped_column(Integer, default=0)
    neu: Mapped[int] = mapped_column(Integer, default=0)
    interest: Mapped[float] = mapped_column(Float, default=0.0)
    zscore: Mapped[float] = mapped_column(Float, default=0.0)

class Baseline(Base):
    __tablename__ = "baselines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    mean: Mapped[float] = mapped_column(Float, default=0.0)
    std: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

def get_user_by_username(db, username: str) -> Optional[User]:
    stmt = select(User).where(User.username == username)
    return db.execute(stmt).scalar_one_or_none()

def create_user(db, username: str, password_hash: str, pro: bool=False) -> User:
    user = User(username=username, password_hash=password_hash, pro=pro)
    db.add(user); db.commit(); db.refresh(user); return user

def set_user_pro(db, username: str, pro: bool) -> Optional[User]:
    user = get_user_by_username(db, username)
    if not user:
        return None
    user.pro = pro
    db.commit(); db.refresh(user)
    return user
