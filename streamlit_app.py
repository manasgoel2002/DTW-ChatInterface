import os
import uuid
from typing import Any, Dict, List

import requests
import streamlit as st


API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")


def api_post(path: str, json: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{API_BASE_URL}{path}"
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
        st.session_state.profile = {}


def sidebar_controls() -> None:
    st.sidebar.header("Settings")
    st.sidebar.text_input("API Base URL", value=API_BASE_URL, key="api_base_url")
    st.sidebar.selectbox("Model", ["gpt-4o-mini"], key="model")
    if st.sidebar.button("Reset Session"):
        st.session_state.history = []
        st.session_state.session_id = f"web-{uuid.uuid4()}"
        st.session_state.profile = {}


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
                profile: Dict[str, Any] = start_data.get("profile", {})
                st.session_state.history = history
                st.session_state.profile = profile
                with st.chat_message("assistant"):
                    st.markdown(reply)
            except Exception as e:
                st.warning(f"Couldn't auto-start onboarding: {e}")

    if st.session_state.user_id:
        st.info(f"User ID: {st.session_state.user_id}")


def chat_section() -> None:
    st.subheader("Onboarding Chat")
    if not st.session_state.user_id:
        st.warning("Create a user first in the Onboarding section.")
        return

    # Show history and current profile
    for turn in st.session_state.history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        with st.chat_message(role):
            st.markdown(content)

    if st.session_state.profile:
        with st.expander("Current Profile", expanded=True):
            st.json(st.session_state.profile)

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
            profile: Dict[str, Any] = data.get("profile", {})
            # Trust server history to keep in sync
            st.session_state.history = history
            st.session_state.profile = profile
            with st.chat_message("assistant"):
                st.markdown(reply)
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
    st.set_page_config(page_title="DTW Chat Interface", page_icon="💬", layout="centered")
    ensure_session_state()
    sidebar_controls()
    st.title("DTW Chat Interface")
    onboarding_section()
    chat_section()
    checkin_section()


if __name__ == "__main__":
    main()


