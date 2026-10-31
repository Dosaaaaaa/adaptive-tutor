"""Create exams (upload a PDF of new concepts, or reuse a quiz bank) and share the student link."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common  # noqa: E402
import streamlit as st  # noqa: E402

from tutor import config, exams, jobs  # noqa: E402

conn = common.get_conn()
st.title("📝 Exams")
st.write("An exam is one quiz for one class. **Create it, send students the link, then open the class report.**")

# ---- create ----
st.header("Create a new exam")
banks = common.list_banks()
source = st.radio("Where do the questions come from?",
                  ["Upload a PDF of the new concepts", "Use a quiz bank that already exists"], horizontal=True)
uploading = source.startswith("Upload")
with st.form("create_exam"):
    title = st.text_input("Exam title", placeholder="For example: Class 10 Physics, Electricity")
    upload, bank_pick, max_concepts = None, None, config.MAX_CONCEPTS
    if uploading:
        upload = st.file_uploader("Study notes (PDF)", type=["pdf"],
                                  help=f"Up to {config.MAX_UPLOAD_MB} MB and {config.MAX_PDF_PAGES} pages. "
                                       "The text must be selectable: scanned pages are not supported yet.")
        max_concepts = st.slider("Most concepts to test", 3, 12, config.MAX_CONCEPTS,
                                 help="The AI finds the main concepts in your PDF. This is the upper limit. "
                                      "A 5-page PDF works well with 5.")
        st.caption("The quiz is written and double-checked by two free AI models. This takes about 10 to 15 minutes "
                   "for a 5-page PDF. You can leave this page and come back.")
    else:
        bank_pick = st.selectbox("Quiz bank", [n for n, _ in banks], format_func=dict(banks).get)
    seats = st.number_input("How many students may join?", 1, 500, 30,
                            help="Once this many students have joined, the link stops letting new students in.")
    go = st.form_submit_button("Create exam", type="primary")

if go:
    try:
        if uploading:
            if upload is None:
                raise jobs.UploadError("Please choose a PDF file first.")
            exam = jobs.create_exam_from_pdf(conn, title, upload.getvalue(), upload.name, int(seats), int(max_concepts))
            note = ("A quiz for this exact file already existed, so the exam is ready now."
                    if exam["reused"] else "The quiz is being prepared. The link will work when it says Open.")
        else:
            if not bank_pick:
                raise exams.ExamError("There is no quiz bank yet. Upload a PDF instead.")
            exam = exams.create_exam(conn, title, int(seats), bank_name=bank_pick)
            note = "The exam is ready."
        st.session_state["just_created"] = (exam["code"], note)
        st.rerun()
    except (exams.ExamError, jobs.UploadError) as exc:
        st.error(str(exc))

if "just_deleted" in st.session_state:
    st.info(st.session_state.pop("just_deleted"))
if "just_created" in st.session_state:
    code, note = st.session_state.pop("just_created")
    st.success(f"Exam **{code}** created. {note}")

# ---- the link ----
with st.expander("Link settings"):
    st.caption(f"Students open the link on their own phone or computer. This computer's address on the current network "
               f"is **{exams.lan_ip()}**. The link only works for students on the **same Wi-Fi**, and only while this address "
               "stays the same: if you change network, send the new link (it is always shown below). Some school and guest "
               "Wi-Fi networks block devices from reaching each other. Then use a phone hotspot, or a tunnel and paste its address here.")
    base = st.text_input("Students reach the app at", value=st.session_state.get("link_base") or exams.public_base())
    st.session_state["link_base"] = base.strip()


@st.fragment(run_every=5)
def build_status(code: str) -> None:
    exam = jobs.refresh(conn, exams.get_exam(conn, code))
    if exam["status"] != "building":
        st.rerun()
    st.progress(exam["progress"], text=exam["message"])
    st.caption("You can leave this page: the quiz keeps being prepared in the background.")


def show(e: dict) -> None:
    with st.container(border=True):
        st.markdown(f"### {e['title']}")
        st.caption(f"Code **{e['code']}** · {common.EXAM_STATUS[e['status']]} · {e['joined']} of {e['max_students']} places used "
                   f"· {e['finished']} finished" + (f" · {e['simulated']} simulated" if e["simulated"] else ""))
        if e["status"] == "building":
            build_status(e["code"])
            if st.button("Stop building", key=f"stop-{e['code']}",
                         help="Stops preparing this quiz. You can start it again later with Try again."):
                jobs.cancel_build(conn, e)
                st.rerun()
        elif e["status"] == "failed":
            st.error(f"The quiz could not be prepared. {e.get('error') or ''}")
            if st.button("Try again", key=f"retry-{e['code']}"):
                try:
                    jobs.retry_build(conn, e)
                    st.rerun()
                except jobs.UploadError as exc:
                    st.error(str(exc))
        else:
            st.markdown("**Student link:** send this to your students")
            st.code(exams.student_link(e["code"], st.session_state.get("link_base")), language=None)
        left, right, _ = st.columns([1, 1, 3])
        if e["status"] in ("ready", "closed") and left.button("Open class report", key=f"open-{e['code']}"):
            st.session_state["exam_code"] = e["code"]
            st.switch_page("teacher/dashboard.py")
        if e["status"] == "ready" and right.button("Close exam", key=f"close-{e['code']}",
                                                   help="Stops new students joining. Students already in can finish."):
            exams.close_exam(conn, e["code"])
            st.rerun()
        if e["status"] == "closed" and right.button("Reopen exam", key=f"reopen-{e['code']}"):
            exams.reopen_exam(conn, e["code"])
            st.rerun()
        with st.expander("Delete this exam"):
            sure = st.checkbox("I understand this deletes the exam and every student's answers", key=f"sure-{e['code']}")
            if st.button("Delete exam", key=f"delete-{e['code']}", disabled=not sure or e["status"] == "building"):
                removed = exams.delete_exam(conn, e["code"])
                jobs.forget_files(e["code"])
                st.session_state["just_deleted"] = f"Deleted “{e['title']}” and {removed} student(s)."
                st.rerun()


st.header("Your exams")
all_exams = exams.list_exams(conn)
if not all_exams:
    st.info("No exams yet. Create the first one above.")
for exam in all_exams:
    show(exam)
