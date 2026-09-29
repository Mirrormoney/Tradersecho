"""Read-only attention map. No upstream or model calls on page views."""
import time
from fastapi import APIRouter, Request, Query
from .community import core

router = APIRouter()

def group_rows(catalog, rows, hours):
    groups = {}
    for ticker, (_, sector) in catalog.items():
        group = groups.setdefault(sector, {'sector': sector, 'stocks': 0, 'measured': 0, 'complete': 0, 'mentions': 0, 'rows': []})
        group['stocks'] += 1
    for row in rows:
        if row['ticker'] not in catalog:
            continue
        group = groups[catalog[row['ticker']][1]]
        group['measured'] += 1
        group['complete'] += int(row.get('coverage_hours', 0) == hours)
        group['mentions'] += row['mentions']
        group['rows'].append(row)
    total = sum(g['mentions'] for g in groups.values())
    for group in groups.values():
        group['share'] = round(100 * group['mentions'] / total, 1) if total else 0
        group['rows'].sort(key=lambda r: (-r['heat'], r['ticker']))
    return sorted(groups.values(), key=lambda g: (-g['mentions'], g['sector']))

@router.get('/api/supply-chain')
def supply_chain(request: Request, window: int = Query(1, ge=1, le=30)):
    from fastapi import HTTPException
    from .count_metrics import enrich
    s = core()
    u = s.account(request)
    if window not in (1, 7, 30):
        raise HTTPException(422, 'Choose 1, 7 or 30 days.')
    if u['demo']:
        return {'groups': [], 'demo': True, 'as_of': None, 'locked': True, 'window': window}
    with s.db() as c:
        now = s.reference('x', c)
        rows = enrich(c, [], now, window)
    groups = group_rows(s.CATALOG, rows, window * 24)
    return {'groups': groups, 'as_of': now, 'stale': time.time() - now > 36 * 3600, 'locked': False, 'window': window}
