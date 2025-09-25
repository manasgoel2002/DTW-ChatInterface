from datetime import time, date
from typing import Any

from pydantic import BaseModel, EmailStr


class OnboardingRequest(BaseModel):
    name: str
    email: EmailStr | None = None


class OnboardingResponse(BaseModel):
    user_id: str
    message: str



class UserProfile(BaseModel):
    age: int | None = None
    date_of_birth: date | None = None
    gender_or_sex: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    sleep_bedtime: time | None = None
    sleep_wake_time: time | None = None
    workout_type: str | None = None
    workout_days_per_week: int | None = None
    physical_activity_profile: str | None = None
    substance_alcohol_per_week: float | None = None
    substance_tobacco_per_day: float | None = None
    substance_caffeine_mg_per_day: float | None = None
    coping_strategies: str | None = None
    preferred_checkin_time: time | None = None
    notification_style: str | None = None
    married_status: str | None = None
    social_support: bool | None = None
    target_sleep_hours: float | None = None
    voice_or_chat_preference: str | None = None


class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str
    model: str | None = None


class ChatResponse(BaseModel):
    reply: str
    history: list[dict[str, str]]
    profile: dict[str, Any] | None = None



