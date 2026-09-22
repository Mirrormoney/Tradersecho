
import os
from dotenv import load_dotenv

# Always load .env from the backend directory explicitly
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# Core settings
DB_URL = os.getenv("DB_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/sentiment")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "change-admin-token")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",") if o.strip()]

# Security
JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# Adapters
ADAPTERS = [a.strip() for a in os.getenv("ADAPTERS", "stocktwits").split(",") if a.strip()]
ADAPTER_TICKERS = [t.strip().upper() for t in os.getenv("ADAPTER_TICKERS", "AAPL,MSFT,TSLA,NVDA,AMZN").split(",") if t.strip()]

# StockTwits config
STOCKTWITS_RATE_PER_MIN = int(os.getenv("STOCKTWITS_RATE_PER_MIN", "60"))

# Reddit config (optional)
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "Tradersecho/1.0 by example")
