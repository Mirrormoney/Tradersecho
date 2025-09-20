import os
from dotenv import load_dotenv
load_dotenv()
APP_HOST=os.getenv('APP_HOST','0.0.0.0')
APP_PORT=int(os.getenv('APP_PORT','8000'))
CORS_ORIGINS=[o.strip() for o in os.getenv('CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(',') if o.strip()]
JWT_SECRET=os.getenv('JWT_SECRET','change-me')
JWT_ALGORITHM=os.getenv('JWT_ALGORITHM','HS256')
ADMIN_TOKEN=os.getenv('ADMIN_TOKEN','change-admin-token')
DB_URL=os.getenv('DB_URL','postgresql+psycopg://postgres:Postgres123@127.0.0.1:5432/sentiment')
REDIS_URL=os.getenv('REDIS_URL','').strip()
USE_REDIS=bool(REDIS_URL)
STRIPE_SECRET_KEY=os.getenv('STRIPE_SECRET_KEY','')
STRIPE_WEBHOOK_SECRET=os.getenv('STRIPE_WEBHOOK_SECRET','')
STRIPE_PRICE_ID=os.getenv('STRIPE_PRICE_ID','')
STRIPE_SUCCESS_URL=os.getenv('STRIPE_SUCCESS_URL','http://localhost:5173/#pro')
STRIPE_CANCEL_URL=os.getenv('STRIPE_CANCEL_URL','http://localhost:5173/#pricing')
