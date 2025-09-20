from fastapi import APIRouter
router=APIRouter(prefix='/api/billing',tags=['billing'])
@router.post('/create-checkout-session')
async def stub(): return {'url': None}
@router.post('/webhook')
async def wh(): return {'received': True}
