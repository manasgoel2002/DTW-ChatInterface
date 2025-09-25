from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple, Set

from dotenv import load_dotenv
from openai import OpenAI
from json import loads as json_loads
from json import JSONDecodeError

from app.api.schemas.onboarding import UserProfile


_history_store: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
_profile_store: Dict[Tuple[str, str], Dict[str, Any]] = {}
_skipped_store: Dict[Tuple[str, str], Set[str]] = {}


def initialize_env() -> None:
    """Load environment variables from .env if present."""
    load_dotenv()


def _get_history(user_id: str, session_id: str) -> List[Dict[str, str]]:
    return _history_store.setdefault((user_id, session_id), [])


def _get_profile(user_id: str, session_id: str) -> Dict[str, Any]:
    return _profile_store.setdefault((user_id, session_id), {})


def _get_skipped(user_id: str, session_id: str) -> Set[str]:
    return _skipped_store.setdefault((user_id, session_id), set())


def _ordered_profile_fields() -> List[str]:
    """Return UserProfile fields in declared order (Pydantic v2)."""
    return list(UserProfile.model_fields.keys())


def _field_hints() -> Dict[str, str]:
    """Human-friendly hints/examples for each field."""
    return {
        "age": "Age in years (e.g., 34)",
        "date_of_birth": "Date of birth in YYYY-MM-DD (e.g., 1991-07-14)",
        "gender_or_sex": "Gender or sex (free text)",
        "height_cm": "Height in centimeters (e.g., 178)",
        "weight_kg": "Weight in kilograms (e.g., 72.5)",
        "sleep_bedtime": "Usual bedtime in HH:MM 24h (e.g., 22:30)",
        "sleep_wake_time": "Usual wake time in HH:MM 24h (e.g., 06:45)",
        "workout_type": "Primary workout type (e.g., running, weights, yoga)",
        "workout_days_per_week": "Workout days per week (0-7)",
        "physical_activity_profile": "Work/activity style (seated, on-feet, manual labor)",
        "substance_alcohol_per_week": "Alcohol drinks per week as a number (e.g., 3)",
        "substance_tobacco_per_day": "Tobacco units per day (e.g., 0, 2)",
        "substance_caffeine_mg_per_day": "Caffeine mg per day (e.g., 150)",
        "coping_strategies": "Coping strategies you use (e.g., mindfulness, journaling)",
        "preferred_checkin_time": "Preferred check-in time HH:MM 24h (e.g., 09:00)",
        "notification_style": "Notification style (push, SMS, email)",
        "married_status": "Marital status (optional)",
        "social_support": "Do you have social support? (yes/no)",
        "target_sleep_hours": "Target hours of sleep per night (e.g., 7.5)",
        "voice_or_chat_preference": "Do you prefer voice or chat?",
    }


def _missing_fields(profile: Dict[str, Any], skipped: Set[str]) -> List[str]:
    return [f for f in _ordered_profile_fields() if f not in profile and f not in skipped]


def _build_system_prompt(profile: Dict[str, Any], skipped: Set[str]) -> str:
    now = datetime.now(timezone.utc).astimezone()
    now_str = now.strftime("%A, %B %d, %Y %I:%M %p %Z")
    hints = _field_hints()
    missing = _missing_fields(profile, skipped)
    next_field = missing[0] if missing else None

    checklist_lines = [f"- {name}: {hints.get(name, '')}".rstrip() for name in _ordered_profile_fields()]
    checklist = "\n".join(checklist_lines)

    next_instr = (
        f"NEXT_FIELD — {next_field}: {hints.get(next_field, '')}\n"
        "Ask EXACTLY ONE short question to collect this field now."
        if next_field
        else "All fields collected or skipped. Offer a brief summary and confirmation."
    )

    return (
        "You are a friendly Digital Twin onboarding agent. Be concise, warm, and supportive.\n"
        f"Current date and time: {now_str}.\n\n"
        "GOAL — Collect ONLY what the user explicitly provides and keep it in session memory.\n"
        "Never infer or fabricate. If unsure, ask a short clarifying question. Accept 'skip' or 'unknown'.\n\n"
        "CHECKLIST — Ask for these Pydantic fields one by one in order (exactly one field per turn):\n"
        f"{checklist}\n\n"
        f"{next_instr}\n\n"
        "STYLE — One concise question per turn. Specify units and formats when helpful (cm, kg, mg/day, HH:MM 24h, YYYY-MM-DD).\n"
        "If the user provides multiple fields, acknowledge and capture them, but next question must continue to the next missing field.\n"
        "Respect privacy; medical details are optional and only captured with explicit consent.\n\n"
        "COMPLETION — When no fields remain, read back a short bullet summary of collected values and ask for confirmation: 'Does this look right? I can save it now.'"
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
    skipped = _get_skipped(user_id, session_id)

    # Determine the field we were targeting before processing this input
    current_missing_before = _missing_fields(profile, skipped)
    targeted_field = current_missing_before[0] if current_missing_before else None

    # Handle explicit skip/unknown for the targeted field
    if targeted_field:
        normalized = user_input.strip().lower()
        if normalized in {"skip", "unknown", "na", "n/a"}:
            skipped.add(targeted_field)

    system_prompt = _build_system_prompt(profile, skipped)
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


