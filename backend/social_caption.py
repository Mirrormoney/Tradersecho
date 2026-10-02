"""Caption policy shared by all ranked organic X editions."""
import re


def validate_ranked_caption(payload):
    rows = payload.get('rows') or []
    if not rows:
        return
    tags = re.findall(r'\$([A-Za-z][A-Za-z0-9.\-]*)', payload['text'])
    if tags != [rows[0]['ticker']]:
        raise ValueError('Ranked captions must contain exactly one cashtag: rank #1. Ranks #2 and #3 belong in the image.')
