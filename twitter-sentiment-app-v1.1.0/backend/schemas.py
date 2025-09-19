from pydantic import BaseModel
class Token(BaseModel):
    access_token: str
    token_type: str
class SignupModel(BaseModel):
    username: str
    password: str
class SentimentItem(BaseModel):
    ticker: str
    interest_score: float
    sentiment: float
    mentions: int
    change_vs_avg: float
class UserOut(BaseModel):
    username: str
    pro: bool