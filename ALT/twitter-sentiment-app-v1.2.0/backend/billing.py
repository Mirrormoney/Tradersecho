import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from auth import get_current_user
from config import STRIPE_SECRET_KEY, STRIPE_PRICE_ID, STRIPE_SUCCESS_URL, STRIPE_CANCEL_URL, STRIPE_WEBHOOK_SECRET
from db import SessionLocal, set_user_pro
router = APIRouter(prefix="/api/billing", tags=["billing"])
@router.post("/create-checkout-session")
async def create_checkout_session(user = Depends(get_current_user)):
    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    stripe.api_key = STRIPE_SECRET_KEY
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        success_url=STRIPE_SUCCESS_URL,
        cancel_url=STRIPE_CANCEL_URL,
        metadata={"username": user["username"]},
    )
    return {"url": session.url}
@router.post("/webhook")
async def webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Stripe webhook secret not configured")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        username = (session.get("metadata") or {}).get("username")
        if username:
            with SessionLocal() as db:
                set_user_pro(db, username, True)
    return {"received": True}