from sqlalchemy import create_engine, Integer, String, Boolean, DateTime, select
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from datetime import datetime
from typing import Optional
from config import DB_URL
engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    pro: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
def get_user_by_username(db, username: str) -> Optional[User]:
    stmt = select(User).where(User.username == username)
    return db.execute(stmt).scalar_one_or_none()
def create_user(db, username: str, password_hash: str, pro: bool = False) -> User:
    user = User(username=username, password_hash=password_hash, pro=pro)
    db.add(user); db.commit(); db.refresh(user); return user
def set_user_pro(db, username: str, pro: bool) -> Optional[User]:
    user = get_user_by_username(db, username)
    if not user: return None
    user.pro = pro; db.commit(); db.refresh(user); return user