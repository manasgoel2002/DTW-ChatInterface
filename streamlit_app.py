import os
import uuid
from typing import Any, Dict, List

import requests
import streamlit as st


API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")


def api_post(path: str, json: Dict[str, Any]) -> Dict[str, Any]:
    base_url = st.session_state.get("api_base_url", API_BASE_URL)
    url = f"{base_url}{path}"
    resp = requests.post(url, json=json, timeout=60)
    resp.raise_for_status()
    return resp.json()


def ensure_session_state() -> None:
    if "user_id" not in st.session_state:
        st.session_state.user_id = ""
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"web-{uuid.uuid4()}"
    if "history" not in st.session_state:
        st.session_state.history = []
    if "profile" not in st.session_state:
        st.session_state.profile = None
    if "api_base_url" not in st.session_state:
        st.session_state.api_base_url = API_BASE_URL


def sidebar_controls() -> None:
    st.sidebar.header("Settings")
    st.sidebar.text_input("API Base URL", value=API_BASE_URL, key="api_base_url")
    st.sidebar.selectbox("Model", ["gpt-4o-mini"], key="model")
    if st.sidebar.button("Reset Session"):
        st.session_state.history = []
        st.session_state.session_id = f"web-{uuid.uuid4()}"
        st.session_state.profile = None
        st.session_state.user_id = ""


def onboarding_section() -> None:
    st.subheader("Onboarding")
    with st.form("onboarding_form"):
        name = st.text_input("Name", value="Alice")
        email = st.text_input("Email (optional)", value="")
        submitted = st.form_submit_button("Create / Get User")
    if submitted:
        payload: Dict[str, Any] = {"name": name}
        if email.strip():
            payload["email"] = email.strip()
        data = api_post("/api/onboarding/", payload)
        st.session_state.user_id = data.get("user_id", "")
        st.success(data.get("message", "Onboarded"))

        # Auto-start onboarding by requesting the first question
        if st.session_state.user_id:
            try:
                start_payload = {
                    "user_id": st.session_state.user_id,
                    "session_id": st.session_state.session_id,
                    "message": "start",
                    "model": st.session_state.get("model", "gpt-4o-mini"),
                }
                start_data = api_post("/api/onboarding/chat", start_payload)
                reply = start_data.get("reply", "")
                history: List[Dict[str, str]] = start_data.get("history", [])
                profile: Dict[str, Any] = start_data.get("profile", None)
                st.session_state.history = history
                st.session_state.profile = profile
                with st.chat_message("assistant"):
                    st.markdown(reply)
                st.rerun()
            except Exception as e:
                st.warning(f"Couldn't auto-start onboarding: {e}")

    if st.session_state.user_id:
        st.info(f"User ID: {st.session_state.user_id}")


def chat_section() -> None:
    col_chat, col_profile = st.columns([2, 1])
    with col_chat:
        st.subheader("Onboarding Chat")
    if not st.session_state.user_id:
        st.warning("Create a user first in the Onboarding section.")
        return

    # Show history
    with col_chat:
        for turn in st.session_state.history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            with st.chat_message(role):
                st.markdown(content)

    # Live profile panel
    with col_profile:
        st.subheader("Live Profile")
        prof = st.session_state.profile
        if prof is None:
            st.caption("No data collected yet.")
        else:
            filled = sum(1 for v in prof.values() if v is not None)
            total = len(prof)
            st.progress(filled / total if total else 0.0, text=f"{filled}/{total} fields")
            # Styled key-value list
            st.markdown('<div class="panel">', unsafe_allow_html=True)
            for k, v in prof.items():
                if v is None:
                    val_html = '<span class="null">NULL</span>'
                else:
                    val_html = f'<span class="val">{v}</span>'
                st.markdown(f'<div><span class="key">{k}</span>: {val_html}</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    with col_chat:
        user_msg = st.chat_input("Message the assistant...")
        if user_msg:
            with st.chat_message("user"):
                st.markdown(user_msg)
            st.session_state.history.append({"role": "user", "content": user_msg})

            payload = {
                "user_id": st.session_state.user_id,
                "session_id": st.session_state.session_id,
                "message": user_msg,
                "model": st.session_state.get("model", "gpt-4o-mini"),
            }
            try:
                data = api_post("/api/onboarding/chat", payload)
                reply = data.get("reply", "")
                history: List[Dict[str, str]] = data.get("history", [])
                profile: Dict[str, Any] = data.get("profile", None)
                # Trust server history to keep in sync
                st.session_state.history = history
                st.session_state.profile = profile
                with st.chat_message("assistant"):
                    st.markdown(reply)
                st.rerun()
            except Exception as e:
                st.error(f"Chat error: {e}")


def checkin_section() -> None:
    st.subheader("Check-in")
    if not st.session_state.user_id:
        st.warning("Create a user first in the Onboarding section.")
        return
    note = st.text_input("Note (optional)")
    if st.button("Submit Check-in"):
        payload = {"user_id": st.session_state.user_id, "note": note or None}
        try:
            data = api_post("/api/checkin/", payload)
            st.success(data.get("message", "Check-in recorded"))
        except Exception as e:
            st.error(f"Check-in error: {e}")


def main() -> None:
    st.set_page_config(page_title="DTW Chat Interface", page_icon="💬", layout="wide")
    # Fixed Light theme palette
    p = {
        "app": "#ffffff",
        "text": "#0f172a",
        "card": "#f8fafc",
        "sidebar": "#f1f5f9",
        "border": "#e2e8f0",
        "accent": "#2563eb",
        "muted": "#64748b",
    }

    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: {p['app']}; color: {p['text']}; }}
        section[data-testid="stSidebar"] {{ background-color: {p['sidebar']}; }}
        h1, h2, h3 {{ color: {p['text']}; }}
        .stMarkdown p {{ line-height: 1.5; }}
        div[data-testid="stChatMessage"] {{ background: {p['card']}; border: 1px solid {p['border']}; }}
        div[role="status"] {{ background: {p['sidebar']}; }}
        .badge {{ display:inline-block; padding:2px 8px; border-radius:12px; font-size:12px; margin-left:6px; background:{p['border']}; color:{p['text']}; }}
        .panel {{ background:{p['sidebar']}; border:1px solid {p['border']}; border-radius:8px; padding:12px; }}
        .key {{ color:{p['accent']}; }}
        .val {{ color:{p['text']}; }}
        .null {{ color:{p['muted']}; font-style:italic; }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    ensure_session_state()
    sidebar_controls()
    st.title("DTW Chat Interface")
    onboarding_section()
    chat_section()
    checkin_section()


if __name__ == "__main__":
    main()


