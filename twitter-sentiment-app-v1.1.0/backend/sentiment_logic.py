from typing import List, Dict, Any, Optional
import random, asyncio
TICKERS = ["AAPL","MSFT","TSLA","NVDA","AMZN","META","GOOGL","NFLX","AMD","INTC"]
def mock_sentiment_for_ticker(ticker: str, live: bool = False) -> Dict[str, Any]:
    base = {"AAPL":400,"MSFT":350,"TSLA":600,"NVDA":500,"AMZN":420,"META":380,"GOOGL":360,"NFLX":280,"AMD":260,"INTC":240}.get(ticker,200)
    m = 1.0 + (random.random() * (0.8 if live else 0.4))
    mentions = int(base * m); interest = mentions / max(1, base)
    sentiment = round(random.uniform(-1, 1), 3); change_vs_avg = round((mentions - base) / max(1, base), 3)
    return {"ticker": ticker, "interest_score": round(interest,3), "sentiment": sentiment, "mentions": mentions, "change_vs_avg": change_vs_avg}
def get_sentiment_list(live: bool = False, tickers: Optional[List[str]] = None, limit: int = 50, sort: Optional[str] = None):
    data = [mock_sentiment_for_ticker(t, live=live) for t in TICKERS]
    if tickers: data = [d for d in data if d["ticker"] in set(tickers)]
    if sort == "mentions": data.sort(key=lambda x: x["mentions"], reverse=True)
    else: data.sort(key=lambda x: x["interest_score"], reverse=True)
    return data[:limit]
async def realtime_stream():
    while True:
        yield get_sentiment_list(live=True, sort="interest_score", limit=50)
        await asyncio.sleep(2)