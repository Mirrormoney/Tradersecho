"""Server-controlled allowances; Founder purchases retain their original limits."""
def limits(c, user):
    founder = bool(c.execute("SELECT 1 FROM billing_entitlements WHERE user_id=? AND tier='founder' AND active=1", (user['id'],)).fetchone())
    staff = user['role'] in ('owner', 'admin')
    if founder or staff:
        return {'saved_stocks': 50, 'personal_voices': 5, 'ticker_refreshes': 5}
    if user['plan'] == 'premium':
        return {'saved_stocks': 25, 'personal_voices': 3, 'ticker_refreshes': 3}
    return {'saved_stocks': 5, 'personal_voices': 0, 'ticker_refreshes': 0}
