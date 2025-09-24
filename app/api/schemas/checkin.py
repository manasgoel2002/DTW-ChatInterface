from datetime import datetime

from pydantic import BaseModel


class CheckinRequest(BaseModel):
    user_id: str
    note: str | None = None
    timestamp: datetime | None = None


class CheckinResponse(BaseModel):
    status: str
    message: str



