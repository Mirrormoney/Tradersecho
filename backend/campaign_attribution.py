"""First-party signup attribution; no advertising identifiers or data sent to X."""
import re
import time
from fastapi import APIRouter, Request
from .community import core, staff

router = APIRouter()
CAMPAIGNS = {
    'signal_audience_test_oct2026': 'Signal Lab',
    'ai_insights_feature_test_oct2026': 'AI Insights',
}

def migrate(c):
    c.execute('''CREATE TABLE IF NOT EXISTS campaign_signups(
        user_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
        campaign TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL)''')

def attach(c, uid, attribution, request):
    if request.headers.get('dnt') == '1' or request.headers.get('sec-gpc') == '1':
        return
    if not isinstance(attribution, dict):
        return
    campaign = attribution.get('campaign')
    if not isinstance(campaign, str) or campaign not in CAMPAIGNS or attribution.get('source') != 'x' or attribution.get('medium') != 'paid_social':
        return
    content = attribution.get('content', '')
    if not isinstance(content, str) or not re.fullmatch(r'[A-Za-z0-9_-]{0,80}', content):
        return
    c.execute('INSERT INTO campaign_signups VALUES(?,?,?,?) ON CONFLICT(user_id) DO NOTHING',
              (uid, campaign, content, time.time()))

def summary(c):
    rows = c.execute('''SELECT s.campaign, COUNT(*) AS signups,
        SUM(CASE WHEN a.email_verified=1 THEN 1 ELSE 0 END) AS verified,
        SUM(CASE WHEN a.email_verified=1 AND a.trial_started_at IS NOT NULL THEN 1 ELSE 0 END) AS trials
        FROM campaign_signups s JOIN accounts a ON a.id=s.user_id
        WHERE a.demo=0 AND a.role='member' GROUP BY s.campaign''').fetchall()
    counts = {r['campaign']: dict(r) for r in rows}
    return {'campaigns': [dict(name=name, **counts.get(key, {
        'campaign': key, 'signups': 0, 'verified': 0, 'trials': 0})) for key, name in CAMPAIGNS.items()]}

@router.get('/api/admin/campaign-results')
def results(request: Request):
    staff(request, owner=True)
    with core().db() as c:
        return summary(c)
