from pydantic import BaseModel
from typing import Optional
class Token(BaseModel): access_token:str; token_type:str
class SignupModel(BaseModel): username:str; password:str
class SentimentItem(BaseModel): ticker:str; interest_score:float; sentiment:float; mentions:int; change_vs_avg:float
class UserOut(BaseModel): username:str; pro:bool
class DailyItem(BaseModel): date:str; ticker:str; mentions:int; interest_score:float; zscore:float; pos:int; neg:int; neu:int
