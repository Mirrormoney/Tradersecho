from fastapi import APIRouter
router = APIRouter(prefix="/api/billing", tags=["billing"])

@router.post("/create-checkout-session")
async def create_checkout_session():
    return {"url": None}

@router.post("/webhook")
async def webhook():
    return {"received": True}
