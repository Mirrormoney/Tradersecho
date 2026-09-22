
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional, List

@dataclass
class RawMention:
    ticker: str
    ts: datetime
    sentiment: str  # 'pos' | 'neg' | 'neu'
    source: str
    external_id: Optional[str]

class Adapter:
    source_name: str = "base"
    def fetch_since(self, since: datetime, tickers: List[str]) -> Iterable[RawMention]:
        raise NotImplementedError
