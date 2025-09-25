from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from openai import OpenAI
from json import loads as json_loads
from json import JSONDecodeError

from app.api.schemas.onboarding import UserProfile


_history_store: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
_profile_store: Dict[Tuple[str, str], Dict[str, Any]] = {}


def initialize_env() -> None:
    """Load environment variables from .env if present."""
    load_dotenv()


def _get_history(user_id: str, session_id: str) -> List[Dict[str, str]]:
    return _history_store.setdefault((user_id, session_id), [])


def _get_profile(user_id: str, session_id: str) -> Dict[str, Any]:
    return _profile_store.setdefault((user_id, session_id), {})


def _build_system_prompt() -> str:
    now = datetime.now(timezone.utc).astimezone()
    now_str = now.strftime("%A, %B %d, %Y %I:%M %p %Z")
    return (
        "You are a very friendly Digital Twin onboarding assistant. Be concise, warm, and supportive.\n"
        f"Current date and time: {now_str}.\n\n"
        "GOAL — Collect ONLY the information the user explicitly provides and keep it in session memory.\n"
        "Never infer or fabricate. If unsure, ask a short clarifying question. Accept 'skip' or 'unknown'.\n\n"
        "CHECKLIST — Gather these fields (one topic at a time):\n"
        "- Age; date of birth; gender or sex\n"
        "- Height (cm) and weight (kg)\n"
        "- Usual sleep schedule: bedtime, wake time\n"
        "- Workout type and days per week\n"
        "- Physical activity profile (e.g., mostly seated, on-feet, manual labor)\n"
        "- Baseline substances: alcohol (drinks/week), tobacco (units/day), caffeine (mg/day)\n"
        "- Coping strategies (e.g., mindfulness, journaling, socializing)\n"
        "- Preferred check-in time and notification style (e.g., push, SMS, email)\n"
        "- Married status (optional)\n"
        "- Social support (yes or no)\n"
        "- Target sleep hours\n"
        "FLOW — Progressive interviewing:\n"
        "1) Start with: 'Tell me about your routine for sleep, work, and movement.'\n"
        "2) Then ask: 'What do you enjoy or avoid in workouts?'\n"
        "3) If they want, invite: 'If you want, share diagnoses or medicines and I will summarize.'\n"
        "4) Clarify substances into simple numbers: alcohol/week, tobacco/day, caffeine mg/day.\n"
        "5) Ask: 'Who do you turn to for support?'\n"
        "6) Gather preferred check-in time and notification style; note voice vs chat preference.\n"
        "7) Ask remaining checklist fields not yet covered.\n\n"
        "STYLE — Keep to at most two concise questions per turn. Use plain language and examples.\n"
        "Specify units when helpful (cm, kg, mg/day, bedtime like 22:30).\n"
        "Respect privacy: treat medical details as optional; only store with explicit user consent.\n\n"
        "SUMMARY — When done, read back a short bullet summary of the collected fields and values.\n"
        "Ask: 'Does this look right? I can save it now.' Do not save until the user confirms."
    )


def _get_openai_client() -> OpenAI:
    return OpenAI()


def _extract_profile_updates(user_input: str) -> Dict[str, Any]:
    """Use the LLM to extract any profile fields present in user_input.

    Returns a partial dict with keys matching UserProfile fields.
    """
    fields = [
        "age",
        "date_of_birth",
        "gender_or_sex",
        "height_cm",
        "weight_kg",
        "sleep_bedtime",
        "sleep_wake_time",
        "workout_type",
        "workout_days_per_week",
        "physical_activity_profile",
        "substance_alcohol_per_week",
        "substance_tobacco_per_day",
        "substance_caffeine_mg_per_day",
        "coping_strategies",
        "preferred_checkin_time",
        "notification_style",
        "married_status",
        "social_support",
        "target_sleep_hours",
        "voice_or_chat_preference",
    ]

    system = (
        "Extract only the fields explicitly stated in the user's message. "
        "Respond as a minimal JSON object with a subset of these keys: "
        + ", ".join(fields)
        + ". Omit any field not present. Use ISO 8601 for dates/times (e.g., 2000-01-31, 22:30)."
    )

    client = _get_openai_client()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_input},
        ],
    )
    content = response.choices[0].message.content or "{}"
    try:
        data = json_loads(content)
        if not isinstance(data, dict):
            return {}
        # Keep only known fields
        return {k: v for k, v in data.items() if k in fields}
    except JSONDecodeError:
        return {}


def generate_onboarding_reply(
    user_id: str,
    session_id: str,
    user_input: str,
    model: str | None = None,
) -> tuple[str, Dict[str, Any]]:
    history = _get_history(user_id, session_id)
    profile = _get_profile(user_id, session_id)

    system_prompt = _build_system_prompt()
    # Build OpenAI chat-completions style messages
    oa_messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role not in ("user", "assistant", "system"):
            role = "user"
        oa_messages.append({"role": role, "content": content})

    oa_messages.append({"role": "user", "content": user_input})

    client = _get_openai_client()
    response = client.chat.completions.create(
        model=model or "gpt-4o-mini",
        messages=oa_messages,
        temperature=0.2,
    )

    # Update memory with the latest turn
    history.append({"role": "user", "content": user_input})
    reply_text = response.choices[0].message.content or ""
    history.append({"role": "assistant", "content": reply_text})

    # Extract and merge profile updates from the user's latest input
    updates = _extract_profile_updates(user_input)
    if updates:
        # Validate and coerce using Pydantic model; merge into existing
        merged = {**profile, **updates}
        try:
            validated = UserProfile(**merged)
            # Drop None values to keep payload minimal
            profile.clear()
            for key, value in validated.model_dump().items():
                if value is not None:
                    profile[key] = value
        except Exception:
            # If validation fails, keep old profile
            pass

    return reply_text, dict(profile)


def get_history(user_id: str, session_id: str) -> List[Dict[str, str]]:
    """Return a simple serializable history for clients."""
    raw = _get_history(user_id, session_id)
    formatted: List[Dict[str, str]] = []
    for msg in raw:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role not in ("user", "assistant", "system"):
            role = "user"
        formatted.append({"role": role, "content": content})
    return formatted


