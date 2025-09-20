
from .base import Adapter, RawMention
from datetime import datetime, timezone
from typing import Iterable, List
import time
import httpx

class StockTwitsAdapter(Adapter):
    source_name = "stocktwits"

    def __init__(self, rate_per_min: int = 60):
        self.rate_per_min = rate_per_min
        self._last_call = 0.0

    def _throttle(self):
        now = time.time()
        min_interval = 60.0 / max(1, self.rate_per_min)
        wait = min_interval - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def fetch_since(self, since: datetime, tickers: List[str]) -> Iterable[RawMention]:
        client = httpx.Client(timeout=15.0)
        out: list[RawMention] = []
        since = since.replace(tzinfo=timezone.utc)
        for t in tickers:
            self._throttle()
            url = f"https://api.stocktwits.com/api/2/streams/symbol/{t}.json"
            try:
                r = client.get(url)
                r.raise_for_status()
                data = r.json()
            except Exception:
                continue
            for msg in data.get("messages", []):
                mid = str(msg.get("id"))
                created_at = msg.get("created_at")
                try:
                    ts = datetime.fromisoformat(created_at.replace("Z","+00:00"))
                except Exception:
                    continue
                if ts.replace(tzinfo=timezone.utc) < since:
                    continue
                st = (msg.get("entities",{}) or {}).get("sentiment",{}) or {}
                basic = st.get("basic")
                if basic == "Bullish": senti = "pos"
                elif basic == "Bearish": senti = "neg"
                else: senti = "neu"
                out.append(RawMention(ticker=t.upper(), ts=ts.replace(tzinfo=None), sentiment=senti, source=self.source_name, external_id=mid))
        return out
