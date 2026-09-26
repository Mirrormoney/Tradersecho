"""Server-side Pro entitlements and October feature release."""
from datetime import datetime, timezone
from fastapi import HTTPException
LAUNCH_AT=datetime(2026,9,30,22,tzinfo=timezone.utc).timestamp()
def launched(now=None):
 import time
 return (time.time() if now is None else now)>=LAUNCH_AT
def has_pro(c,u):
 if not u or u.get('demo') or u.get('status','active')!='active':return False
 return bool(u.get('role') in ('owner','admin') or u.get('plan')=='pro' or c.execute("SELECT 1 FROM billing_entitlements WHERE user_id=? AND active=1 AND tier IN ('founder','pro_monthly','pro_yearly')",(u['id'],)).fetchone())
def require_pro(request):
 from . import service as s
 u=s.account(request)
 with s.db() as c:allowed=has_pro(c,u)
 if not allowed:raise HTTPException(403,'Upgrade to Pro to open the full analysis.')
 if u['role'] not in ('owner','admin') and not launched():raise HTTPException(403,'Full access opens October 1.')
 return u
