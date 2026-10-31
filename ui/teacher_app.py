"""Teacher app. Private: it listens on this computer only, and it asks for the teacher password.

Create an exam (upload a PDF of new concepts, or reuse a quiz bank), send students the link, then read the class report.
"""
import hmac
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
import streamlit as st  # noqa: E402

from tutor import config, exams  # noqa: E402

st.set_page_config(page_title="Teacher", page_icon="👩‍🏫", layout="wide")


def gate() -> None:
    """Nothing in the teacher area is shown until the teacher password has been typed."""
    password = config.read_env_file().get("TEACHER_PASSWORD")
    if not password:
        st.title("👩‍🏫 Teacher area")
        st.error("No teacher password is set. Add a line `TEACHER_PASSWORD=choose-a-password` to the `.env` file, "
                 "then reload this page.")
        st.stop()
    if st.session_state.get("teacher_ok"):
        return
    st.title("👩‍🏫 Teacher area")
    wait = st.session_state.get("locked_until", 0) - time.time()
    if wait > 0:
        st.error(f"Too many wrong passwords. Please try again in {int(wait) + 1} seconds.")
        st.stop()
    with st.form("login"):
        typed = st.text_input("Teacher password", type="password")
        go = st.form_submit_button("Open", type="primary")
    if go:
        if hmac.compare_digest(typed.strip().encode(), password.encode()):   # spaces from copy and paste do not matter
            st.session_state.update(teacher_ok=True, failures=0)
            st.rerun()
        fails = st.session_state.get("failures", 0) + 1
        st.session_state["failures"] = fails
        if fails >= 5:
            st.session_state.update(locked_until=time.time() + 60, failures=0)
        time.sleep(1)                                    # slows down guessing
        st.error("That password is not right.")
    st.stop()


gate()

conn = common.get_conn()
try:
    exams.adopt_legacy(conn, config.resolve_bank().name)   # keep any earlier trial students in a demo exam
except FileNotFoundError:
    pass

with st.sidebar:
    st.caption("Teacher area: only on this computer")
    if st.button("Log out"):
        st.session_state.clear()
        st.rerun()

navigation = st.navigation([
    st.Page("teacher/exams.py", title="Exams", icon="📝", default=True),
    st.Page("teacher/dashboard.py", title="Class report", icon="📊"),
    st.Page("teacher/status.py", title="System", icon="⚙️"),
])
navigation.run()
