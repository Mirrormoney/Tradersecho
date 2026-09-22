
import os
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

DB_URL = os.getenv("DB_URL")
if not DB_URL:
    print("❌ No DB_URL found in .env")
    raise SystemExit(1)

try:
    engine = create_engine(DB_URL, future=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        print(f"✅ Connected successfully using {DB_URL}")
        print("➡️  Next step: run 'alembic upgrade head'")
except SQLAlchemyError as e:
    print("❌ Failed to connect:", e)
    raise SystemExit(1)
