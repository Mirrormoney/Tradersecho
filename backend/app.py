from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from typing import List, Dict, Any, Optional
from datetime import datetime
from config import CORS_ORIGINS, ADMIN_TOKEN
from auth import create_access_token, verify_password, get_password_hash, get_current_user
from db import SessionLocal, create_user, get_user_by_username, set_user_pro
from schemas import Token, SignupModel, UserOut, DailyItem, SentimentItem
from sentiment_logic import get_free_daily, get_live_snapshot
from billing import router as billing_router


import re
from config import DB_URL
_safe_url = re.sub(r':[^:@]+@', ':***@', DB_URL)
print(f"🔗 Using DB: {_safe_url}")

app = FastAPI(title="Twitter Sentiment API", version="1.4.2")

app.include_router(billing_router)

app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/api/health")
async def health(): return {"ok": True, "time": datetime.utcnow().isoformat()}

@app.get("/api/me", response_model=UserOut)
async def me(user: Dict[str, Any] = Depends(get_current_user)): return UserOut(username=user["username"], pro=user["pro"])

@app.post("/api/auth/signup", response_model=Token)
async def signup(payload: SignupModel):
    with SessionLocal() as db:
        if get_user_by_username(db, payload.username):
            raise HTTPException(status_code=400, detail="Username already exists")
        hashed = get_password_hash(payload.password); create_user(db, payload.username, hashed, pro=False)
        access_token = create_access_token({"sub": payload.username}); return Token(access_token=access_token, token_type="bearer")

@app.post("/api/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    with SessionLocal() as db:
        user = get_user_by_username(db, form_data.username)
        if not user or not verify_password(form_data.password, user.password_hash):
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        access_token = create_access_token({"sub": user.username}); return Token(access_token=access_token, token_type="bearer")

@app.post("/api/admin/make-pro", response_model=UserOut)
async def admin_make_pro(username: str, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_TOKEN: raise HTTPException(status_code=401, detail="Unauthorized")
    with SessionLocal() as db:
        user = set_user_pro(db, username, True)
        if not user: raise HTTPException(status_code=404, detail="User not found")
        return UserOut(username=user.username, pro=user.pro)

@app.get("/api/free/daily", response_model=List[DailyItem])
async def free_daily(tickers: Optional[str] = None, date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None), sort: Optional[str] = "interest_score", limit: int = 50, page: int = 1):
    return get_free_daily(tickers.split(",") if tickers else None, date_from, date_to, limit, page, sort)

@app.get("/api/pro/snapshot", response_model=List[SentimentItem])
async def pro_snapshot(window: Optional[str] = "5m", user: Dict[str, Any] = Depends(get_current_user)):
    if not user.get("pro"): raise HTTPException(status_code=403, detail="Upgrade to Pro to access this endpoint")
    return get_live_snapshot(limit=50)

@app.websocket("/ws/realtime")
async def ws_realtime(ws: WebSocket):
    token = ws.query_params.get("token")
    try:
        user = get_current_user(token=token)
        if not user.get("pro"):
            await ws.close(code=4403)
            return
    except Exception:
        await ws.close(code=4401)
        return
    await ws.accept()
    try:
        import asyncio
        while True:
            payload = get_live_snapshot(limit=50)
            await ws.send_json(payload)
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        pass
