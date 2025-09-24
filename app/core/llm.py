from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Tuple

from dotenv import load_dotenv
from openai import OpenAI


_history_store: Dict[Tuple[str, str], List[Dict[str, str]]] = {}


def initialize_env() -> None:
    """Load environment variables from .env if present."""
    load_dotenv()


def _get_history(user_id: str, session_id: str) -> List[Dict[str, str]]:
    return _history_store.setdefault((user_id, session_id), [])


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


def generate_onboarding_reply(
    user_id: str,
    session_id: str,
    user_input: str,
    model: str | None = None,
) -> str:
    history = _get_history(user_id, session_id)

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

    return reply_text


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


