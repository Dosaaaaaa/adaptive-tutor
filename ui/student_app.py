"""Student app: the page behind the link. It only lets a student take their own exam. There is no way from here to the
teacher's dashboard (that is a different app, on a different port, that only listens on the teacher's computer).

Flow: open the link (?exam=CODE) -> choose a nickname -> answer, with a reason each time -> see your score at the very end.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
import streamlit as st  # noqa: E402

from tutor import config, exams, jobs, scoring, service  # noqa: E402
from tutor.service import TutorError  # noqa: E402

st.set_page_config(page_title="Exam", page_icon="🎓", layout="centered")
conn = common.get_conn()


def forget_student() -> None:
    st.session_state.pop("sid", None)
    if "sid" in st.query_params:
        del st.query_params["sid"]


# ---- which exam? (from the link, or typed in) ----
code = exams.normalize(st.query_params.get("exam") or st.session_state.get("exam_code"))
exam = exams.get_exam(conn, code) if code else None
if exam is None:
    st.title("🎓 Take your exam")
    if code:
        st.error("We could not find that exam. Check the link or the code with your teacher.")
    with st.form("code"):
        typed = st.text_input("Exam code", help="Your teacher gives you this code, or a link that has it in.")
        go = st.form_submit_button("Continue", type="primary")
    if go and typed.strip():
        st.query_params["exam"] = exams.normalize(typed)
        st.rerun()
    st.stop()
if exam["status"] == "building":                 # a build that finished while nobody had the teacher page open
    exam = jobs.refresh(conn, exam)
st.session_state["exam_code"] = exam["code"]
bank = common.get_bank(exam["bank_name"]) if exam["bank_name"] and exam["status"] in ("ready", "closed") else None
judge, _ = common.get_judge(exam["bank_name"]) if bank else (None, "")

# ---- who is this? (the id lives in the link too, so a reload carries on where the student was) ----
sid = st.session_state.get("sid") or st.query_params.get("sid")
if sid and exams.student_exam(conn, sid) != exam["code"]:
    forget_student()
    sid = None
elif sid:
    st.session_state["sid"] = sid

# ---- 1. join ----
if not sid:
    st.title(f"🎓 {exam['title']}")
    st.write(f"You will answer multiple-choice questions in up to 3 short rounds. For every answer, write **one or two "
             f"sentences on why you picked it** (at least {config.MIN_REASON_WORDS} words), or tick *I am guessing*. "
             "You will not be told which answers were right until the very end, when you will see your score.")
    with st.form("join"):
        nickname = st.text_input("Your nickname (not your real name)", max_chars=30)
        go = st.form_submit_button("Start the exam", type="primary")
    if go:
        try:
            sid = exams.join_exam(conn, exam["code"], nickname)
        except (exams.ExamError, TutorError) as exc:
            st.error(str(exc))
            st.stop()
        st.session_state["sid"] = sid
        st.query_params["sid"] = sid
        st.rerun()
    st.stop()


def run_judge() -> None:
    with st.spinner("Checking your reasoning…"):
        service.finish_round(conn, bank, sid, judge)
    st.rerun()


# ---- 3. the score (only after the last round) ----
def show_results() -> None:
    res = service.results(conn, bank, sid)
    score = scoring.score_for(conn, sid)
    st.title("✅ You are done")
    st.write(f"Thank you, **{res['student']['nickname']}**.")
    if score["percent"] is not None:
        st.markdown(f"## Your score: {score['credited']} out of {score['asked']} ({score['percent']}%)")
        st.caption("The score counts the main questions. A right answer with a reason that shows a misunderstanding does "
                   "not count, and the extra follow-up questions are not part of it.")
    st.subheader("Concept by concept")
    for c in res["concepts"]:
        line = f"{common.STATE_ICON[c['state']]} **{c['name']}**: {common.STATE_TEXT[c['state']]}"
        st.markdown(line + ("" if c["state"] == "understood" else f" · read page {c['page']} again"))
    if res["review"]:
        st.subheader("Answers to look at again")
        for r in res["review"]:
            with st.expander(f"{r['concept']}: {r['question']}"):
                st.markdown(f"**Your answer:** {r['your_answer']}")
                if r["was_right_choice"]:
                    st.markdown("Your choice was right, but your reason did not match the idea in the notes.")
                st.markdown(f"**Right answer:** {r['correct_answer']}")
                if r["your_reason"]:
                    st.markdown(f"**Your reason:** *{r['your_reason']}*")
                if r["misconception"]:
                    st.markdown(f"**The idea to fix:** {r['misconception']}")
                st.markdown(f"**Why:** {r['explanation']}  \n📖 Page {r['page']} of the notes")
    st.info("Your teacher will see the results for the whole class. You can close this page now.")


if bank is None:
    st.error("This exam is not available any more. Please ask your teacher.")
    st.stop()
p = service.progress(conn, bank, sid)
if p.phase == "judge_pending":
    run_judge()
if p.phase == "done":
    show_results()
    st.stop()

# ---- 2. one question ----
view = service.current_question(conn, bank, sid)
qid = view["question_id"]
t0 = st.session_state.setdefault(f"t0-{qid}", time.time())      # when this question was first shown

st.caption(f"{exam['title']} · Round {view['round']} of 3")
st.progress((view["index"] - 1) / view["total"], text=f"Question {view['index']} of {view['total']}")
labels = {o["key"]: f"{o['label']}.  {o['text']}" for o in view["options"]}
with st.form(f"q-{qid}"):
    st.subheader(view["stem"])
    choice = st.radio("Pick one answer", [o["key"] for o in view["options"]], format_func=labels.get,
                      index=None, label_visibility="collapsed")
    reason = st.text_area("Why did you pick this? Write one or two sentences.", placeholder="I chose this because…", height=90)
    guess = st.checkbox("I am guessing")
    submitted = st.form_submit_button("Submit answer", type="primary")

if submitted:
    if choice is None:
        st.warning("Please pick an answer first.")
        st.stop()
    try:
        result = service.submit_answer(conn, bank, sid, qid, choice, reason, guess, seconds=round(time.time() - t0, 1))
    except TutorError as exc:
        st.error(str(exc))
        st.stop()
    if result["round_complete"]:
        run_judge()
    st.rerun()
