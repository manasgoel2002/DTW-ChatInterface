from uuid import uuid4

from fastapi import APIRouter

from ..schemas.onboarding import (
    OnboardingRequest,
    OnboardingResponse,
    ChatRequest,
    ChatResponse,
)
from ...core.llm import generate_onboarding_reply, get_history


router = APIRouter(tags=["onboarding"])


@router.post("/", response_model=OnboardingResponse, summary="Onboard a new user")
def onboard_user(payload: OnboardingRequest) -> OnboardingResponse:
    user_id = str(uuid4())
    name_part = payload.name.strip()
    return OnboardingResponse(user_id=user_id, message=f"Welcome {name_part}!")


@router.post("/chat", response_model=ChatResponse, summary="Onboarding chat message")
def onboarding_chat(payload: ChatRequest) -> ChatResponse:
    reply, profile = generate_onboarding_reply(
        user_id=payload.user_id,
        session_id=payload.session_id,
        user_input=payload.message,
        model=payload.model,
    )
    history = get_history(payload.user_id, payload.session_id)
    return ChatResponse(reply=reply, history=history, profile=profile)



