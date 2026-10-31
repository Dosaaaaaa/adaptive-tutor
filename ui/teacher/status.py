"""What the system is using: quiz banks, AI keys, database."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common  # noqa: E402
import streamlit as st  # noqa: E402

from tutor import config, exams, llm, stats  # noqa: E402

conn = common.get_conn()
st.title("⚙️ System")

st.subheader("AI")
keys = {p.name: bool(config.api_key(p.key_env)) for p in llm.PROVIDERS.values()}
st.markdown("**API keys found in `.env`:** " + ", ".join(f"{n}: {'yes' if ok else 'no'}" for n, ok in keys.items()))
problem = None
try:
    llm.assert_independent(llm.from_env("generator"), llm.from_env("verifier"))
except llm.ConfigError as exc:
    problem = str(exc)
if problem:
    st.warning(f"A new PDF cannot be turned into a quiz yet. {problem}")
else:
    st.success("A new PDF can be turned into a quiz (writer and checker are set and are different AI families).")
st.caption("Run `python -m tutor.smoke` in a terminal to test the keys and models.")

st.subheader("Quiz banks on this computer")
for _, label in common.list_banks():
    st.markdown(f"- {label}")

st.subheader("Database")
counts = stats.table_counts(conn)
st.markdown(f"`{config.db_path()}`: {counts['students']} students, {counts['answers']} answers, "
            f"{len(exams.list_exams(conn))} exams")
st.subheader("Where students go")
st.markdown(f"Students use **{exams.public_base()}** (the link on each exam). The teacher area is only on this computer "
            f"(port {config.TEACHER_PORT}).")
