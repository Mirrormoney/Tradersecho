from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from typing import List, Dict, Any
from datetime import datetime

from auth import create_access_token, verify_password, get_password_hash, get_current_user
from database import init_db, get_user_by_username, create_user
from sentiment_logic import get_delayed_sentiment, get_realtime_sentiment_stream
from schemas import Token, SignupModel, SentimentItem

app = FastAPI(title="Twitter Sentiment API", version="1.0.5")

origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    init_db()

@app.get("/api/health")
async def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

@app.post("/api/auth/signup", response_model=Token)
async def signup(payload: SignupModel):
    if get_user_by_username(payload.username):
        raise HTTPException(status_code=400, detail="Username already exists")
    hashed = get_password_hash(payload.password)
    create_user(payload.username, hashed)
    access_token = create_access_token({"sub": payload.username})
    return Token(access_token=access_token, token_type="bearer")

@app.post("/api/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token({"sub": user["username"]})
    return Token(access_token=access_token, token_type="bearer")

@app.get("/api/free/daily", response_model=List[SentimentItem])
async def free_daily():
    return get_delayed_sentiment()

@app.get("/api/pro/realtime", response_model=List[SentimentItem])
async def pro_realtime(user: Dict[str, Any] = Depends(get_current_user)):
    return get_delayed_sentiment(live=True)

@app.websocket("/ws/realtime")
async def ws_realtime(ws: WebSocket):
    token = ws.query_params.get("token")
    try:
        _ = get_current_user(token=token)  # Validate explicit token for WS
    except Exception:
        await ws.close(code=4401)
        return
    await ws.accept()
    try:
        async for payload in get_realtime_sentiment_stream():
            await ws.send_json(payload)
    except WebSocketDisconnect:
        pass