
from .base import Adapter, RawMention
from datetime import datetime
from typing import Iterable, List
import re

try:
    import praw  # optional
except Exception:
    praw = None

CASHTAG = re.compile(r"\$([A-Z]{1,6})")

class RedditAdapter(Adapter):
    source_name = "reddit"

    def __init__(self, client_id: str=None, client_secret: str=None, user_agent: str=None):
        self.client_id=client_id; self.client_secret=client_secret; self.user_agent=user_agent

    def fetch_since(self, since: datetime, tickers: List[str]) -> Iterable[RawMention]:
        if not praw or not self.client_id or not self.client_secret or not self.user_agent:
            return []
        reddit = praw.Reddit(client_id=self.client_id, client_secret=self.client_secret, user_agent=self.user_agent)
        subs = ["stocks", "wallstreetbets", "investing"]
        out=[]
        for s in subs:
            for post in reddit.subreddit(s).new(limit=200):
                ts = datetime.fromtimestamp(post.created_utc)
                if ts < since: 
                    continue
                text = f"{post.title}\n{post.selftext or ''}"
                found = set(m.group(1).upper() for m in CASHTAG.finditer(text))
                use = found.intersection(set(t.upper() for t in tickers))
                if not use:
                    continue
                for t in use:
                    out.append(RawMention(ticker=t, ts=ts, sentiment="neu", source=self.source_name, external_id=f"t3_{post.id}"))
        return out
