from __future__ import annotations

from datetime import datetime, timezone, date, time
import re
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
    """Return missing fields, excluding ones that are redundant given known values.

    Smart rules:
    - If date_of_birth is known, age is considered derived and not asked.
    - If age is known but date_of_birth is missing, do not force asking DOB (privacy-friendly).
    """
    base = [f for f in _ordered_profile_fields() if f not in profile and f not in skipped]
    # Redundancy pruning
    if "date_of_birth" in profile:
        base = [f for f in base if f != "age"]
    if "age" in profile:
        base = [f for f in base if f != "date_of_birth"]
    return base


def _apply_derived_fields(profile: Dict[str, Any]) -> None:
    """Populate derived fields from existing values (in-place).

    - age from date_of_birth
    """
    if profile.get("date_of_birth") and not profile.get("age"):
        try:
            dob: date = profile["date_of_birth"] if isinstance(profile["date_of_birth"], date) else date.fromisoformat(str(profile["date_of_birth"]))
            today = datetime.now(timezone.utc).date()
            years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if years >= 0:
                profile["age"] = years
        except Exception:
            # Leave age unset if parsing fails
            pass
def _to_int(value: str) -> int | None:
    match = re.search(r"-?\d+", value)
    if not match:
        return None
    try:
        return int(match.group(0))
    except Exception:
        return None


def _to_float(value: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def _to_time(value: str) -> time | None:
    value = value.strip()
    m = re.search(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b", value)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    ss = int(m.group(3)) if m.group(3) else 0
    try:
        return time(hour=hh, minute=mm, second=ss)
    except Exception:
        return None


def _to_date(value: str) -> date | None:
    m = re.search(r"\b\d{4}-\d{2}-\d{2}\b", value)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(0))
    except Exception:
        return None


def _to_bool(value: str) -> bool | None:
    v = value.strip().lower()
    if v in {"yes", "y", "true", "1"}:
        return True
    if v in {"no", "n", "false", "0"}:
        return False
    return None


def _extract_from_labeled_lines(user_input: str) -> Dict[str, Any]:
    """Parse simple 'Label: value' lines with common synonyms.

    If multiple lines map to the same field, the later one wins.
    """
    label_to_field: Dict[str, str] = {
        "AGE": "age",
        "DATE OF BIRTH": "date_of_birth",
        "GENDER": "gender_or_sex",
        "GENDER OR SEX": "gender_or_sex",
        "HEIGHT": "height_cm",
        "HEIGHT CM": "height_cm",
        "WEIGHT": "weight_kg",
        "USUAL BEDTIME": "sleep_bedtime",
        "BEDTIME": "sleep_bedtime",
        "USUAL WAKE TIME": "sleep_wake_time",
        "WAKE TIME": "sleep_wake_time",
        "PRIMARY WORKOUT TYPE": "workout_type",
        "WORKOUT TYPE": "workout_type",
        "WORKOUT DAYS PER WEEK": "workout_days_per_week",
        "WORK/ACTIVITY STYLE": "physical_activity_profile",
        "PHYSICAL ACTIVITY PROFILE": "physical_activity_profile",
        "ALCOHOL CONSUMPTION": "substance_alcohol_per_week",
        "TOBACCO CONSUMPTION": "substance_tobacco_per_day",
        "CAFFEINE CONSUMPTION": "substance_caffeine_mg_per_day",
        "COPING STRATEGIES": "coping_strategies",
        "PREFERRED CHECK-IN TIME": "preferred_checkin_time",
        "NOTIFICATION STYLE": "notification_style",
        "MARITAL STATUS": "married_status",
        "SOCIAL SUPPORT": "social_support",
        "TARGET SLEEP HOURS": "target_sleep_hours",
        "COMMUNICATION PREFERENCE": "voice_or_chat_preference",
        "VOICE OR CHAT PREFERENCE": "voice_or_chat_preference",
    }

    updates: Dict[str, Any] = {}
    for raw_line in user_input.splitlines():
        if ":" not in raw_line:
            continue
        label_part, value_part = raw_line.split(":", 1)
        label = label_part.strip().upper()
        value = value_part.strip()
        field = label_to_field.get(label)
        if not field:
            continue

        parsed: Any = None
        if field in {"age", "workout_days_per_week"}:
            parsed = _to_int(value)
        elif field in {"height_cm", "weight_kg", "substance_alcohol_per_week", "substance_tobacco_per_day", "substance_caffeine_mg_per_day", "target_sleep_hours"}:
            parsed = _to_float(value)
        elif field in {"sleep_bedtime", "sleep_wake_time", "preferred_checkin_time"}:
            parsed = _to_time(value)
        elif field == "date_of_birth":
            parsed = _to_date(value)
        elif field == "social_support":
            parsed = _to_bool(value)
        elif field in {"gender_or_sex", "workout_type", "physical_activity_profile", "coping_strategies", "notification_style", "married_status", "voice_or_chat_preference"}:
            parsed = value.lower()

        if parsed is not None:
            updates[field] = parsed

    return updates


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
        "SMART RULES —\n"
        "- Avoid redundant questions. If date_of_birth is present, derive age yourself and DO NOT ask for age.\n"
        "- If age is present but date_of_birth is missing, do not force asking for date_of_birth unless the user volunteers it.\n"
        "- Do not re-ask for fields that are already known unless the user indicates a correction.\n"
        "- If the user provides multiple values at once, capture all of them, then proceed to the next missing field.\n"
        "- If a newly provided value conflicts with an existing one (e.g., age vs DOB), prefer date_of_birth and ask a brief confirmation about the discrepancy.\n\n"
        "INPUT STYLES YOU MUST ACCEPT —\n"
        "- Free text answers (e.g., 'I usually sleep at 22:30').\n"
        "- Multi-line blocks of 'Label: value' pairs (e.g., 'Age: 22', 'Usual Bedtime: 01:00', 'Preferred Check-in Time: 08:30').\n"
        "- JSON objects with keys matching the profile fields.\n"
        "Normalize values to the expected units and formats.\n\n"
        "VALIDATION & FORMATS —\n"
        "- Dates: YYYY-MM-DD. Times: HH:MM (24h).\n"
        "- Workout days per week: 0–7. Target sleep hours: 0–24.\n"
        "- Plausibility checks (not strict): age 0–120, height 50–250 cm, weight 20–300 kg, alcohol 0–50/week, tobacco 0–100/day, caffeine 0–1000 mg/day. If a value seems implausible, ask one concise clarification before storing.\n"
        "- Booleans: yes/no, y/n, true/false.\n\n"
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
    """Extract profile fields from user_input.

    Tries LangChain structured output with the Pydantic model for reliability,
    falls back to direct OpenAI JSON mode if LangChain is unavailable.
    """
    # Attempt LangChain structured output first
    try:
        # Delayed imports so the module works even if LangChain isn't installed
        from langchain_openai import ChatOpenAI  # type: ignore
        from langchain_core.prompts import ChatPromptTemplate  # type: ignore

        system = (
            "You extract only explicitly provided fields from the user's message. "
            "Return a structured object matching the Pydantic schema. "
            "For any field not clearly present, leave it null. "
            "Use ISO 8601 for dates (YYYY-MM-DD) and 24h time (HH:MM)."
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                ("user", "{input}"),
            ]
        )

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        structured_llm = llm.with_structured_output(UserProfile)
        chain = prompt | structured_llm
        result = chain.invoke({"input": user_input})

        # Normalize to dict and remove None values (only send updates)
        if hasattr(result, "model_dump"):
            data: Dict[str, Any] = result.model_dump()
        elif isinstance(result, dict):
            data = result
        else:
            data = {}
        langchain_updates = {k: v for k, v in data.items() if v is not None}
        # Also parse any labeled lines supplied by the user and merge (user-specified wins)
        labeled = _extract_from_labeled_lines(user_input)
        return {**langchain_updates, **labeled}
    except Exception:
        # Fallback: OpenAI JSON mode
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
            json_updates = {k: v for k, v in data.items() if k in fields and v is not None}
            labeled = _extract_from_labeled_lines(user_input)
            return {**json_updates, **labeled}
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

    # Apply derived values before deciding what to ask next
    _apply_derived_fields(profile)

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

    # Re-apply derived values in case new inputs unlock them (e.g., DOB -> age)
    _apply_derived_fields(profile)

    # Build a complete profile view including keys with nulls for the client UI
    full_profile = UserProfile(**profile).model_dump(exclude_none=False)
    return reply_text, full_profile


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


