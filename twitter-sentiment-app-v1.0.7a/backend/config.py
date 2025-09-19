import os
from dotenv import load_dotenv
load_dotenv()
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS","http://localhost:5173").split(",") if o.strip()]
JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "change-admin-token")
DB_URL = os.getenv("DB_URL", "sqlite:///./app.db")
REDIS_URL = os.getenv("REDIS_URL", "").strip()
USE_REDIS = bool(REDIS_URL)