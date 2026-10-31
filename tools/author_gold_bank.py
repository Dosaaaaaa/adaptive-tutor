#!/usr/bin/env python3
"""Author the gold quiz bank for demo/Electricity_Basics.pdf (SPEC 14, Plan B).

Written by hand (by Claude in Claude Code), not by the free-API pipeline. It serves three jobs:
  1. a bank to build and test the student side, the judge and the dashboard before API keys exist,
  2. a reference to score the free-API pipeline against (tutor/eval.py),
  3. a demo fallback when Wi-Fi or an API is down.
Every quote is checked against the real PDF text. Run:  .venv/bin/python tools/author_gold_bank.py
"""
from __future__ import annotations

import random
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tutor import config  # noqa: E402
from tutor.extract import extract_pages, pdf_sha256  # noqa: E402
from tutor.models import Bank, Concept, Edge, Evidence, Misconception, Option, Question, save_bank  # noqa: E402
from tutor.quotes import find_page  # noqa: E402

PDF = ROOT / "demo" / "Electricity_Basics.pdf"
OUT = config.BANK_DIR / "electricity_gold"
OHM = "Ω"

CONCEPTS = [
    ("C1", "Electric current", 1, "Current is the rate of flow of charge, measured in amperes with an ammeter in series.",
     "Electric current is the flow of electric charge through a conductor."),
    ("C2", "Potential difference (voltage)", 2, "The energy given to each coulomb of charge, measured in volts with a voltmeter in parallel.",
     "Charge flows round a circuit only if something pushes it."),
    ("C3", "Resistance", 3, "Opposition to current, measured in ohms. Depends on length, thickness, material and temperature.",
     "This opposition to the flow of current is called resistance."),
    ("C4", "Ohm's law", 4, "V = I x R links potential difference, current and resistance.",
     "Ohm’s law links the three quantities."),
    ("C5", "Series circuits", 5, "One path: same current everywhere, potential differences add, resistances add.",
     "In a series circuit the components are connected one after another, so there is only one path for the charge to follow."),
]
EDGES = [
    ("C1", "C2", "Concept 2 begins: Recall from Concept 1 that current is a flow of charge."),
    ("C1", "C3", "Concept 3 begins: Recall from Concept 1 that current is a flow of charge."),
    ("C2", "C4", "Concept 4: The potential difference (Concept 2) pushes the current round the circuit."),
    ("C3", "C4", "Concept 4: the resistance (Concept 3) limits how big the current can be."),
    ("C4", "C5", "Concept 5: Ohm’s law (Concept 4) can be used to analyse a series circuit."),
]
# id, statement, contrast quote (verbatim from the PDF)
MISC = [
    ("M1.1", "Current is the amount of charge stored in the wire, not a rate of flow.",
     "Current is the rate of flow of charge."),
    ("M1.2", "An ammeter is connected in parallel, across the component.",
     "An ammeter must be connected in series with the component, so that all of the current flows through it."),
    ("M1.3", "Current can still flow and light the bulb when the circuit has a gap, because the current just goes to the bulb.",
     "Current flows only in a complete circuit."),
    ("M2.1", "Potential difference flows through the wires, like current does.",
     "Potential difference is always measured between two points. It does not flow through a wire."),
    ("M2.2", "A voltmeter is connected in series, like an ammeter.",
     "A voltmeter must be connected in parallel, across the component being measured."),
    ("M2.3", "Voltage is the same thing as energy, so a 12 V cell gives 12 J whatever the amount of charge.",
     "A potential difference of one volt means one joule of energy for each coulomb of charge."),
    ("M3.1", "A thicker wire has more resistance, because there is more material in the way.",
     "A thicker wire has a smaller resistance than a thinner wire of the same material and length."),
    ("M3.2", "A hotter metal wire lets charge through more easily, so its resistance falls.",
     "The resistance of a metal wire rises when the wire gets hotter"),
    ("M3.3", "The resistance of a wire changes whenever the voltage or the current changes.",
     "For a metal wire at constant temperature, the resistance stays the same whatever the potential difference across it or the current through it."),
    ("M4.1", "A larger resistance gives a larger current for the same potential difference.",
     "When the potential difference stays constant, doubling the resistance halves the current."),
    ("M4.2", "Doubling the potential difference doubles the resistance, so the current stays the same.",
     "When the resistance stays constant, doubling the potential difference doubles the current."),
    ("M4.3", "The current against potential difference graph of a filament bulb is a straight line, like a wire.",
     "The graph for a filament bulb is a curve"),
    ("M5.1", "Current is used up as it passes through each component, so it is smaller after each bulb.",
     "The current is the same at every point in a series circuit"),
    ("M5.2", "Current divides between the components in a series circuit, like water splitting into branches.",
     "In a series circuit there is only one path for the charge."),
    ("M5.3", "Each component in a series circuit gets the full potential difference of the cell.",
     "The potential differences across the components add up to the potential difference of the supply: V total = V1 + V2 + V3."),
]

# concept, kind, stem, correct, [(distractor, tag) x3], rationale, evidence quote (verbatim from the PDF)
Q = [
    ("C1", "recall", "What does the electric current in a wire tell you?", "Charge passing a point each second",
     [("The amount of charge stored in the wire", "M1.1"), ("The total number of electrons in the wire", "M1.1"),
      ("The energy carried by each coulomb of charge", "other")],
     "Current is the rate of flow of charge: the charge that passes a point each second.",
     "Current is the rate of flow of charge. It is the amount of charge that passes a point in a circuit each second."),
    ("C1", "recall", "How must an ammeter be connected into a circuit?", "In series with the component",
     [("In parallel, across the component", "M1.2"), ("In parallel with the cell only", "M1.2"),
      ("On a separate wire outside the loop", "other")],
     "An ammeter is connected in series so that all of the current flows through it.",
     "An ammeter must be connected in series with the component, so that all of the current flows through it."),
    ("C1", "apply", "A wire carries a current of 2 A. How much charge passes a point in the wire in 5 s?", "10 C",
     [("2 C", "M1.1"), ("0.4 C", "other"), ("7 C", "other")],
     "Q = I × t = 2 × 5 = 10 C.", "It can be rearranged as Q = I × t."),
    ("C1", "apply", "A cell is joined to a bulb by one wire only. The other terminal of the bulb is not connected to "
     "anything. What happens to the current?", "There is no current, because the circuit is not complete",
     [("A small current flows, because the wire touches the cell", "M1.3"),
      ("The bulb still lights, because it uses the current that arrives", "M1.3"),
      ("Current flows in the wire but not through the bulb", "other")],
     "Current flows only in a complete circuit, so a break stops the current in the whole loop.",
     "Current flows only in a complete circuit. A break anywhere in the loop stops the current in the whole loop."),
    ("C1", "tiebreak", "What does a current of 3 A mean?", "3 C of charge passes a point each second",
     [("3 coulombs of charge are stored in the wire", "M1.1"), ("3 joules of energy are given to each coulomb", "other"),
      ("3 electrons pass a point every second", "other")],
     "A current of 3 A means 3 coulombs of charge pass a point every second.",
     "A current of one ampere means that one coulomb of charge passes a point every second. A current of 2 A means that 2 coulombs pass a point every second."),
    ("C1", "simple", "Which quantity does an ammeter measure?", "Current",
     [("Charge", "M1.1"), ("Potential difference", "other"), ("Resistance", "other")],
     "An ammeter measures current.", "Current is measured with an ammeter."),

    ("C2", "recall", "What is potential difference between two points?", "Energy per coulomb of charge",
     [("The amount of charge passing each second", "other"), ("The opposition of a component to current", "other"),
      ("The total energy stored in the cell", "M2.3")],
     "Potential difference is the energy transferred to or from each coulomb of charge as it moves between the points.",
     "Potential difference (voltage) between two points is the energy transferred to or from each coulomb of charge as it moves between those points."),
    ("C2", "recall", "How must a voltmeter be connected to measure the potential difference across a component?",
     "In parallel, across the component",
     [("In series with the component", "M2.2"), ("In series, on the wire leaving the cell", "M2.2"),
      ("Anywhere, because position does not matter", "other")],
     "A voltmeter is connected in parallel, across the component being measured.",
     "A voltmeter must be connected in parallel, across the component being measured."),
    ("C2", "apply", "A 12 V cell moves 3 C of charge through a circuit. How much energy does the cell transfer to the charge?",
     "36 J", [("12 J", "M2.3"), ("4 J", "other"), ("15 J", "other")],
     "W = V × Q = 12 × 3 = 36 J.", "It can be rearranged as W = V × Q."),
    ("C2", "apply", "A student says that a potential difference of 6 V flows along the wire from one point to another. "
     "What is wrong with this?", "Potential difference is the push between two points, and the charge is what flows",
     [("Nothing is wrong, because potential difference flows round the circuit like current", "M2.1"),
      ("Nothing is wrong, but the 6 V is used up along the wire", "M2.1"),
      ("The energy should flow, not the potential difference", "other")],
     "Potential difference is measured between two points and does not flow. The charge flows, pushed by it.",
     "It does not flow through a wire. The charge flows, and the potential difference is the push that makes it flow."),
    ("C2", "tiebreak", "A bulb transfers 48 J of energy while 8 C of charge passes through it. What is the potential "
     "difference across the bulb?", "6 V", [("48 V", "M2.3"), ("384 V", "other"), ("40 V", "other")],
     "V = W / Q = 48 / 8 = 6 V.",
     "The formula is V = W / Q, where V is the potential difference in volts (V), W is the energy in joules (J) and Q is the charge in coulombs (C)."),
    ("C2", "simple", "Which part of a simple circuit gives energy to the charge?", "The cell",
     [("The bulb", "other"), ("The voltmeter", "other"), ("The wire", "other")],
     "A cell transfers energy to the charge.", "A cell transfers energy to the charge."),

    ("C3", "recall", "Two wires are made of the same material and have the same length. Which has the smaller resistance?",
     "The thicker wire",
     [("The thinner wire", "M3.1"), ("They have the same resistance", "other"), ("It depends only on the current", "M3.3")],
     "A thicker wire has a smaller resistance than a thinner wire of the same material and length.",
     "A thicker wire has a smaller resistance than a thinner wire of the same material and length."),
    ("C3", "recall", "What happens to the resistance of a metal wire when the wire gets hotter?", "It rises",
     [("It falls", "M3.2"), ("It stays the same", "other"), ("It drops to zero", "M3.2")],
     "A hotter metal wire has a higher resistance: the atoms vibrate more and collide with more of the moving charge.",
     "The resistance of a metal wire rises when the wire gets hotter, because the atoms vibrate more and collide with more of the moving charge."),
    ("C3", "apply", f"A wire has a resistance of 12 {OHM}. A second wire has the same material and length but twice the "
     f"cross-sectional area. What is the resistance of the second wire?", f"6 {OHM}",
     [(f"24 {OHM}", "M3.1"), (f"12 {OHM}", "other"), (f"10 {OHM}", "other")],
     f"Doubling the cross-sectional area halves the resistance: 12 / 2 = 6 {OHM}.",
     "If the cross-sectional area is doubled, the resistance is halved."),
    ("C3", "apply", "The potential difference across a metal wire at constant temperature is doubled. What happens to "
     "the resistance of the wire?", "It stays the same",
     [("It doubles", "M3.3"), ("It halves", "M3.3"), ("It falls to zero as the charge speeds up", "other")],
     "At constant temperature the resistance of a metal wire stays the same whatever the potential difference.",
     "For a metal wire at constant temperature, the resistance stays the same whatever the potential difference across it or the current through it."),
    ("C3", "tiebreak", "Wire Q has the same material and thickness as wire P, but wire Q is twice as long. How do their "
     "resistances compare?", "Wire Q has twice the resistance of wire P",
     [("Wire Q has half the resistance of wire P", "other"), ("The two wires have the same resistance", "other"),
      ("Wire Q has less resistance, because it is longer", "other")],
     "If the length is doubled, the resistance is doubled.", "If the length is doubled, the resistance is doubled."),
    ("C3", "simple", "Which material is used for connecting wires because it has a low resistance?", "Copper",
     [("Nichrome", "other"), ("Rubber", "other"), ("Steel", "other")],
     "Copper has a low resistance, so it is used for connecting wires.",
     "Copper has a low resistance, so it is used for connecting wires."),

    ("C4", "recall", "The resistance in a circuit stays constant and the potential difference is doubled. What happens "
     "to the current?", "It doubles",
     [("It halves", "other"), ("It stays the same", "M4.2"), ("It is multiplied by four", "other")],
     "When the resistance stays constant, doubling the potential difference doubles the current.",
     "When the resistance stays constant, doubling the potential difference doubles the current."),
    ("C4", "recall", "What is the shape of the current against potential difference graph for a filament bulb?", "A curve",
     [("A straight line through the origin", "M4.3"), ("A horizontal line", "other"), ("A vertical line", "other")],
     "The graph for a filament bulb is a curve because the filament gets hot and its resistance rises.",
     "The graph for a filament bulb is a curve, because the filament gets hot and its resistance rises as the current increases."),
    ("C4", "apply", f"A 24 V supply is connected across an 8 {OHM} resistor. What current flows?", "3 A",
     [("192 A", "other"), ("16 A", "other"), ("0.33 A", "other")],
     "I = V / R = 24 / 8 = 3 A.", "The law can be rearranged as I = V / R and as R = V / I."),
    ("C4", "apply", "The potential difference across a resistor stays at 6 V, and the resistor is replaced by one with "
     "twice the resistance. What happens to the current?", "It halves",
     [("It doubles", "M4.1"), ("It stays the same", "other"), ("It is multiplied by four", "M4.1")],
     "When the potential difference stays constant, doubling the resistance halves the current.",
     "When the potential difference stays constant, doubling the resistance halves the current."),
    ("C4", "tiebreak", "Which equation is Ohm’s law?", "V = I × R",
     [("V = I / R", "other"), ("I = V × R", "other"), ("R = I / V", "other")],
     "Ohm’s law states that V = I × R.",
     "Ohm’s law states that V = I × R, where V is the potential difference in volts, I is the current in amperes and R is the resistance in ohms."),
    ("C4", "simple", "To find a current using Ohm’s law, which two quantities must you know?",
     "Potential difference and resistance",
     [("The potential difference and the charge", "other"), ("The resistance and the energy", "other"),
      ("Only the resistance of the circuit", "other")],
     "To find any one of V, I or R, you must know the other two.",
     "To find any one of V, I or R, you must know the other two."),

    ("C5", "recall", "A student places ammeters before, between and after two bulbs connected in series. How do the "
     "three readings compare?", "All three readings are the same",
     [("The first reading is the largest and the last is the smallest", "M5.1"),
      ("The middle reading is half of the first reading", "M5.2"),
      ("They are the same only if the bulbs are identical", "other")],
     "The current is the same at every point in a series circuit.",
     "An ammeter placed before, between or after the components of a series circuit shows the same reading."),
    ("C5", "recall", "How is the total resistance of resistors in series found?", "Add the individual resistances",
     [("Multiply the individual resistances together", "other"), ("Take the largest of the individual resistances", "other"),
      ("Take the smallest of the individual resistances", "other")],
     "The total resistance in series is the sum of the individual resistances.",
     "The total resistance of components in series is the sum of their resistances: R total = R1 + R2 + R3."),
    ("C5", "apply", f"A 10 V cell is connected in series with a 2 {OHM} resistor and a 3 {OHM} resistor. What is the "
     f"potential difference across the 3 {OHM} resistor?", "6 V",
     [("10 V", "M5.3"), ("5 V", "other"), ("4 V", "other")],
     f"R total = 5 {OHM}, I = 10 / 5 = 2 A, so the potential difference across the 3 {OHM} resistor is 2 × 3 = 6 V.",
     "The total resistance of components in series is the sum of their resistances: R total = R1 + R2 + R3."),
    ("C5", "apply", "Two identical bulbs are connected in series with a 6 V cell. What is the potential difference across "
     "each bulb?", "3 V", [("6 V", "M5.3"), ("12 V", "other"), ("1.5 V", "other")],
     "Identical bulbs in series share the potential difference of the cell equally: 6 / 2 = 3 V.",
     "Two identical bulbs in series with a cell share the potential difference of the cell equally."),
    ("C5", "tiebreak", "A third resistor is added in series to a circuit, and the supply stays the same. What happens to "
     "the current?", "It gets smaller",
     [("It stays the same", "other"), ("It gets larger", "other"), ("It splits into three smaller currents", "M5.2")],
     "Adding a resistor in series increases the total resistance, so the current gets smaller.",
     "Adding another resistor in series increases the total resistance, so the current in the circuit gets smaller."),
    ("C5", "simple", "How many paths are there for the charge in a series circuit?", "One",
     [("Two", "M5.2"), ("As many as there are components", "M5.2"), ("None", "other")],
     "In a series circuit there is only one path for the charge.",
     "In a series circuit there is only one path for the charge."),
]


def build() -> Bank:
    pages = extract_pages(PDF)
    problems: list[str] = []

    def page_of(quote: str, what: str) -> int:
        p = find_page(quote, pages)
        if p is None:
            problems.append(f"quote not found in the PDF ({what}): {quote[:70]}")
        return p or 0

    concepts = []
    for cid, name, page, summary, quote in CONCEPTS:
        if page_of(quote, f"concept {cid}") != page:
            problems.append(f"{cid}: quote is not on page {page}")
        concepts.append(Concept(id=cid, name=name, summary=summary, page=page, quote=quote))
    misc = []
    for mid, statement, contrast in MISC:
        page_of(contrast, mid)
        misc.append(Misconception(id=mid, concept_id="C" + mid[1], statement=statement, contrast_quote=contrast))

    questions, counter = [], {}
    for cid, kind, stem, correct, wrongs, rationale, quote in Q:
        counter[(cid, kind)] = counter.get((cid, kind), 0) + 1
        qid = f"{cid}-{kind}-{counter[(cid, kind)]}"
        order = [(correct, "correct")] + list(wrongs)
        random.Random(f"gold:{qid}").shuffle(order)
        opts = [Option(key="ABCD"[i], text=t, tag=tag) for i, (t, tag) in enumerate(order)]
        key = next(o.key for o in opts if o.tag == "correct")
        questions.append(Question(
            id=qid, concept_id=cid, kind=kind, round=config.ROUND_OF_KIND[kind], stem=stem, options=opts,
            answer_key=key, rationale=rationale, evidence=Evidence(page=page_of(quote, qid), quote=quote),
            checks={"grounded": True, "authored_by": "claude", "llm_gates": "not run"}))
    if problems:
        sys.exit("Problems:\n  " + "\n  ".join(problems))

    manifest = {
        "name": "electricity_gold", "pdf": PDF.name, "pdf_sha256": pdf_sha256(PDF), "created": str(date.today()),
        "source": "authored by Claude in Claude Code (SPEC 14 Plan B). Deterministic gates only; no LLM gates run.",
        "models": {}, "max_concepts": config.MAX_CONCEPTS,
    }
    return Bank(manifest, pages, concepts, [Edge(parent=p, child=c, why=w) for p, c, w in EDGES], misc, questions)


if __name__ == "__main__":
    bank = build()
    save_bank(bank, OUT)
    keys = [q.answer_key for q in bank.questions]
    print(f"wrote {OUT}: {len(bank.concepts)} concepts, {len(bank.edges)} edges, {len(bank.misconceptions)} "
          f"misconceptions, {len(bank.questions)} questions")
    print("answer key spread:", {k: keys.count(k) for k in "ABCD"})
