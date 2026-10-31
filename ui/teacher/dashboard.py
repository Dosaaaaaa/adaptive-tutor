"""Class report for one exam: concept-first, plain words, counts not probabilities (SPEC 11), plus every student's score."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from tutor import config, exams, scoring, stats  # noqa: E402
from tutor.simulate import clear_simulated, simulate_class  # noqa: E402

conn = common.get_conn()
st.title("📊 Class report")

open_exams = [e for e in exams.list_exams(conn) if e["status"] in ("ready", "closed")]
if not open_exams:
    st.info("There is no exam to report on yet. Create one on the Exams page.")
    st.stop()
codes = [e["code"] for e in open_exams]
chosen = st.session_state.get("exam_code")
code = st.selectbox("Exam", codes, index=codes.index(chosen) if chosen in codes else 0,
                    format_func=lambda c: f"{next(e['title'] for e in open_exams if e['code'] == c)} ({c})")
st.session_state["exam_code"] = code
exam = exams.get_exam(conn, code)
bank = common.get_bank(exam["bank_name"])
now = exams.counts(conn, code)
st.caption(f"{now['joined']} of {exam['max_students']} places used · {now['finished']} finished · "
           f"student link: {exams.student_link(code, st.session_state.get('link_base'))}")

# ---- sidebar ----
with st.sidebar:
    st.header("Show")
    pick = st.radio("Students", ["All", "Real only", "Simulated only"],
                    help="Simulated students are test data. They are never mixed in silently.")
    include = {"All": "all", "Real only": "real", "Simulated only": "simulated"}[pick]
    only_done = st.checkbox("Only students who finished", value=True)
    auto = st.checkbox("Update automatically", value=True, help="Refreshes the report every 15 seconds while students take the test.")
    st.button("Refresh", icon="🔄")
    with st.expander("Test data (simulated students)"):
        n_sim = st.number_input("How many", 1, 60, 14)
        seed = st.number_input("Random seed", 0, 9999, 7)
        if st.button("Add simulated students"):
            with st.spinner("Simulating…"):
                exams.attach(conn, simulate_class(conn, bank, int(n_sim), int(seed)), code)
            st.rerun()
        sure = st.checkbox("I understand this deletes all simulated students")
        if st.button("Remove simulated students", disabled=not sure):
            st.toast(f"Removed {clear_simulated(conn)} simulated students")
            st.rerun()


def dot(rep: dict) -> str:
    esc = lambda t: t.replace('"', '\\"')  # noqa: E731
    out = ["digraph G {", "rankdir=LR;", 'bgcolor="transparent";',
           'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=13, fontcolor="white", margin="0.22,0.14"];',
           'edge [color="#6b7280", arrowsize=0.8];']
    for n in rep["graph"]["nodes"]:
        out.append(f'"{n["id"]}" [label="{esc(n["name"])}\\n{n["understood"]} of {n["n"]} understood", '
                   f'fillcolor="{common.STATUS_COLOR[n["status"]]}"];')
    out += [f'"{p}" -> "{c}";' for p, c in rep["graph"]["edges"]]
    return "\n".join(out + ["}"])


def report() -> None:
    rep = stats.class_report(conn, bank, include=include, only_done=only_done, exam=code)
    s = rep["students"]
    st.caption(f"{s['counted']} students shown ({s['real']} real, {s['simulated']} simulated)"
               + (f" · {s['in_progress']} still taking the test" if s["in_progress"] else ""))
    if s["simulated"]:
        st.info(f"This view includes {s['simulated']} **simulated** students (test data).")
    if s["counted"] == 0:
        st.warning("No finished students yet. Send students the link, or add simulated students in the sidebar.")
        return

    st.header("Re-teach these first")
    if not rep["cards"]:
        st.success("No concept needs re-teaching: most of the class understood every concept.")
    for i, c in enumerate(rep["cards"], 1):
        with st.container(border=True):
            st.markdown(f"### {i}. {c['name']}   {common.STATUS_ICON[c['status']]} {c['status_label']}")
            st.markdown(f"**{c['headline']}.**")
            if c["start_here"]:
                st.markdown(f"🚩 **START HERE.** This is the first gap for {c['root_count']} of {c['n']} students.")
            if c["top_mistake"]:
                t = c["top_mistake"]
                st.markdown(f"Most common mistake: *“{t['statement']}”* ({t['students']} students)")
            if c["holds_back"]:
                st.markdown("Also holds back: " + ", ".join(c["holds_back"]))
            st.markdown(f"📖 Re-read: page {c['page']}")
            if c["top_mistake"] and c["top_mistake"]["quotes"]:
                with st.expander("What students wrote"):
                    for q in c["top_mistake"]["quotes"]:
                        st.markdown(f"> {q}")

    st.header("Concept map")
    st.caption("Read from left to right: learn the concepts on the left first. Number = students who understood it.")
    st.graphviz_chart(dot(rep), use_container_width=True)
    st.caption("🟢 Class has it (75% or more understood)   🟠 Shaky (50% to 75%)   🔴 Missing (under 50%)")

    t_s, t_q, t_m, t_d = st.tabs(["Scores", "Questions", "Mistakes", "Data and build"])

    with t_s:
        sc = scoring.exam_scores(conn, bank, code, include, only_done)
        if sc["average"] is not None:
            a, b, c = st.columns(3)
            a.metric("Class average", f"{sc['average']}%")
            b.metric("Highest", f"{sc['best']}%")
            c.metric("Lowest", f"{sc['lowest']}%")
        st.caption("Score = answers counted as right among the main questions (the same for every student). "
                   "A right answer with a reason that shows a misunderstanding is not counted.")
        table = pd.DataFrame([{"Student": r["nickname"] + ("  (simulated)" if r["simulated"] else ""),
                               "Score": f"{r['credited']} / {r['asked']}", "%": r["percent"],
                               **{bank.concept(cid).name: common.STATE_ICON[v] for cid, v in r["states"].items()}}
                              for r in sc["students"]])
        st.dataframe(table, hide_index=True, use_container_width=True,
                     column_config={"%": st.column_config.ProgressColumn("%", min_value=0, max_value=100, format="%d%%")})
        st.caption("🟢 understood · 🟠 shaky · 🔴 missing")

    with t_q:
        qs = stats.question_stats(conn, bank, include=include, exam=code)
        st.caption("Hardest first. Difficulty is measured from the students' answers, not guessed. "
                   "Round 3 questions were only seen by students who struggled earlier.")
        flag_text = {"check_question": "check this question", "too_easy": "too easy", "order_broken": "easy question is harder"}
        df = pd.DataFrame([{"Question": q["question_id"], "Concept": bank.concept(q["concept_id"]).name, "Type": q["kind"],
                            "Students": q["n"], "Right": f'{q["k"]} of {q["n"]}',
                            "% right": round(q["p"] * 100) if q["n"] else None, "Difficulty": q["label"],
                            "Flags": ", ".join(flag_text[f] for f in q["flags"])} for q in qs])
        col = st.column_config
        st.dataframe(df, hide_index=True, use_container_width=True, column_config={
            "Question": col.TextColumn(width="medium"), "Concept": col.TextColumn(width="medium"),
            "Type": col.TextColumn(width="small"), "Students": col.NumberColumn(width="small"),
            "Right": col.TextColumn(width="small"), "% right": col.NumberColumn(width="small"),
            "Difficulty": col.TextColumn(width="small"), "Flags": col.TextColumn(width="large")})
        pick_q = st.selectbox("Look at one question", [q["question_id"] for q in qs])
        q = next(x for x in qs if x["question_id"] == pick_q)
        st.markdown(f"**{q['stem']}**")
        st.dataframe(pd.DataFrame([{"Option": o["text"], "Chosen by": o["picked"],
                                    "Type": "RIGHT ANSWER" if o["tag"] == "correct" else (
                                        bank.misconception(o["tag"]).statement if bank.misconception(o["tag"]) else "other wrong answer")}
                                   for o in q["options"]]), hide_index=True, use_container_width=True)

    with t_m:
        if not rep["mistakes"]:
            st.write("No misconceptions found yet.")
        for m in rep["mistakes"]:
            with st.expander(f"{m['students']} students · {m['concept']}: “{m['statement']}”"):
                for quote in m["quotes"]:
                    st.markdown(f"> {quote}")
        if rep["other_texts"]:
            st.subheader("Other wrong ideas that are not on the list")
            for o in rep["other_texts"]:
                st.markdown(f"- {bank.concept(o['concept_id']).name}: {o['text']}")

    with t_d:
        counts = stats.table_counts(conn)
        cols = st.columns(4)
        for col_, name in zip(cols, ("students", "answers", "judgements", "mastery_log")):
            col_.metric(name, counts[name])
        st.download_button("Download this exam's answers (CSV)",
                           pd.DataFrame(stats.export_rows(conn, bank, exam=code)).to_csv(index=False),
                           file_name=f"answers_{code}.csv", mime="text/csv")
        st.subheader("How the quiz bank was built")
        st.json(bank.manifest, expanded=False)
        build_report = config.BANK_DIR / bank.name / "build_report.md"
        if build_report.exists():
            st.markdown(build_report.read_text(encoding="utf-8"))
        else:
            st.caption("No build report for this bank (it was written by hand, not by the automatic pipeline).")


(st.fragment(run_every=15)(report) if auto else report)()
