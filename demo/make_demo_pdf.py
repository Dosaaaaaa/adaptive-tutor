#!/usr/bin/env python3
"""Build demo/Electricity_Basics.pdf: 5 pages, 5 concepts, one concept per page.

The text is original, written for this project. It states every fact and every worked
answer in plain sentences, so the quiz-bank pipeline can quote it word for word.
It does NOT list "common mistakes": the pipeline must find the misconceptions itself.

Concept graph the PDF is written to produce (see demo/expected.json):
    C1 Current -> C2 Voltage -> C4 Ohm's law -> C5 Series circuits
    C1 Current -> C3 Resistance -> C4 Ohm's law

Usage:  pip install reportlab && python demo/make_demo_pdf.py
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

OUT = Path(__file__).with_name("Electricity_Basics.pdf")
OHM = "Ω"  # Greek capital omega

# DejaVu Sans carries the omega and multiplication signs we need.
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/Library/Fonts"]
for d in FONT_DIRS:
    regular, bold = Path(d, "DejaVuSans.ttf"), Path(d, "DejaVuSans-Bold.ttf")
    if regular.exists() and bold.exists():
        pdfmetrics.registerFont(TTFont("Body", str(regular)))
        pdfmetrics.registerFont(TTFont("Body-Bold", str(bold)))
        pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body", boldItalic="Body-Bold")
        break
else:
    raise SystemExit("DejaVu Sans not found: edit FONT_DIRS in make_demo_pdf.py")

INK, MUTED, ACCENT, BOX = (colors.HexColor(c) for c in ("#1B2430", "#5B6675", "#1F5FBF", "#EEF3FA"))

label = ParagraphStyle("label", fontName="Body-Bold", fontSize=8.5, leading=11, textColor=MUTED)
title = ParagraphStyle("title", fontName="Body-Bold", fontSize=25, leading=30, textColor=INK, spaceAfter=8)
head = ParagraphStyle("head", fontName="Body-Bold", fontSize=12.5, leading=16, textColor=ACCENT, spaceBefore=14, spaceAfter=5)
body = ParagraphStyle("body", fontName="Body", fontSize=11.8, leading=17.4, textColor=INK)
fact = ParagraphStyle("fact", parent=body, leftIndent=20, bulletIndent=0, spaceAfter=5, bulletFontName="Body-Bold")

# (title, key idea, facts, worked examples)
CONCEPTS = [
    ("Electric current",
     "Electric current is the flow of electric charge through a conductor. In a metal wire the moving "
     "charges are electrons. The bigger the current, the more charge passes a point in the wire every second.",
     ["Current is the rate of flow of charge. It is the amount of charge that passes a point in a circuit each second.",
      "The formula is I = Q / t, where I is the current in amperes (A), Q is the charge in coulombs (C) and t is the "
      "time in seconds (s). It can be rearranged as Q = I × t.",
      "A current of one ampere means that one coulomb of charge passes a point every second. A current of 2 A means "
      "that 2 coulombs pass a point every second.",
      "Current is measured with an ammeter. An ammeter must be connected in series with the component, so that all of "
      "the current flows through it.",
      "Current flows only in a complete circuit. A break anywhere in the loop stops the current in the whole loop.",
      "By convention, current is drawn flowing from the positive terminal of a cell, round the circuit, to the negative "
      "terminal. The electrons move the opposite way, from the negative terminal to the positive terminal."],
     ["<b>Example 1.</b> A charge of 12 C passes a point in a wire in 4 s. I = Q / t = 12 / 4 = 3 A. The current is 3 A.",
      "<b>Example 2.</b> How much charge passes a point in 10 s when the current is 0.5 A? "
      "Q = I × t = 0.5 × 10 = 5 C."]),

    ("Potential difference (voltage)",
     "Recall from Concept 1 that current is a flow of charge. Charge flows round a circuit only if something pushes it. "
     "The push comes from a cell or battery, which gives energy to the charge. The energy given to each coulomb of "
     "charge is called the potential difference, or voltage.",
     ["Potential difference (voltage) between two points is the energy transferred to or from each coulomb of charge as "
      "it moves between those points.",
      "The formula is V = W / Q, where V is the potential difference in volts (V), W is the energy in joules (J) and Q "
      "is the charge in coulombs (C). It can be rearranged as W = V × Q.",
      "A potential difference of one volt means one joule of energy for each coulomb of charge. A 9 V battery gives 9 J "
      "to every coulomb that passes through it.",
      "A cell transfers energy to the charge. A component such as a bulb transfers energy from the charge to its "
      "surroundings as heat and light.",
      "Potential difference is measured with a voltmeter. A voltmeter must be connected in parallel, across the "
      "component being measured.",
      "Potential difference is always measured between two points. It does not flow through a wire. The charge flows, "
      "and the potential difference is the push that makes it flow."],
     ["<b>Example 1.</b> A 9 V battery moves 2 C of charge through a circuit. W = V × Q = 9 × 2 = 18 J. "
      "The battery transfers 18 J of energy.",
      "<b>Example 2.</b> A bulb transfers 30 J of energy while 5 C of charge passes through it. V = W / Q = 30 / 5 = 6 V. "
      "The potential difference across the bulb is 6 V."]),

    ("Resistance",
     "Recall from Concept 1 that current is a flow of charge. As the charges move through a material they collide with "
     "its atoms, so the material opposes the flow. This opposition to the flow of current is called resistance.",
     ["Resistance is the opposition of a component or wire to the flow of electric current.",
      f"Resistance is measured in ohms (symbol {OHM}).",
      "A longer wire has a greater resistance than a shorter wire of the same material and thickness. If the length is "
      "doubled, the resistance is doubled.",
      "A thicker wire has a smaller resistance than a thinner wire of the same material and length. If the "
      "cross-sectional area is doubled, the resistance is halved.",
      "Different materials have different resistances. Copper has a low resistance, so it is used for connecting wires. "
      "Nichrome has a high resistance, so it is used in heating elements.",
      "The resistance of a metal wire rises when the wire gets hotter, because the atoms vibrate more and collide with "
      "more of the moving charge.",
      "For a metal wire at constant temperature, the resistance stays the same whatever the potential difference across "
      "it or the current through it."],
     [f"<b>Example 1.</b> A wire has a resistance of 6 {OHM}. A second wire is made of the same material and has the same "
      f"thickness, but it is three times as long. Its resistance is 3 × 6 = 18 {OHM}.",
      f"<b>Example 2.</b> A third wire has the same material and length as the first wire, but twice the cross-sectional "
      f"area. Its resistance is 6 / 2 = 3 {OHM}."]),

    ("Ohm’s law",
     "Concept 2 and Concept 3 meet here. The potential difference (Concept 2) pushes the current round the circuit, and "
     "the resistance (Concept 3) limits how big the current can be. Ohm’s law links the three quantities.",
     ["Ohm’s law states that V = I × R, where V is the potential difference in volts, I is the current in "
      "amperes and R is the resistance in ohms.",
      "The law can be rearranged as I = V / R and as R = V / I.",
      "When the resistance stays constant, doubling the potential difference doubles the current.",
      "When the potential difference stays constant, doubling the resistance halves the current.",
      "A graph of current against potential difference for a metal wire at constant temperature is a straight line "
      "through the origin.",
      "The graph for a filament bulb is a curve, because the filament gets hot and its resistance rises as the current "
      "increases.",
      "To find any one of V, I or R, you must know the other two."],
     [f"<b>Example 1.</b> A 12 V supply is connected across a 6 {OHM} resistor. I = V / R = 12 / 6 = 2 A.",
      f"<b>Example 2.</b> A current of 0.5 A flows through a resistor when the potential difference across it is 8 V. "
      f"R = V / I = 8 / 0.5 = 16 {OHM}."]),

    ("Series circuits",
     "Ohm’s law (Concept 4) can be used to analyse a series circuit. In a series circuit the components are "
     "connected one after another, so there is only one path for the charge to follow.",
     ["In a series circuit there is only one path for the charge.",
      "The current is the same at every point in a series circuit, because the charge has no other path to take and "
      "cannot pile up or disappear along the way.",
      "An ammeter placed before, between or after the components of a series circuit shows the same reading.",
      "The potential differences across the components add up to the potential difference of the supply: "
      "V total = V1 + V2 + V3.",
      "The total resistance of components in series is the sum of their resistances: R total = R1 + R2 + R3.",
      "Adding another resistor in series increases the total resistance, so the current in the circuit gets smaller.",
      "Two identical bulbs in series with a cell share the potential difference of the cell equally. If the resistances "
      "are different, the component with the larger resistance gets the larger share of the potential difference."],
     [f"<b>Example.</b> A 12 V cell is connected in series with a 4 {OHM} resistor and an 8 {OHM} resistor. "
      f"R total = 4 + 8 = 12 {OHM}. I = V / R = 12 / 12 = 1 A. The same 1 A flows through both resistors. "
      f"Across the 4 {OHM} resistor: V = I × R = 1 × 4 = 4 V. Across the 8 {OHM} resistor: "
      f"V = 1 × 8 = 8 V. Check: 4 V + 8 V = 12 V, which equals the potential difference of the cell."]),
]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Body", 8.5)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(A4[0] / 2, 12 * mm, f"Page {doc.page} of {len(CONCEPTS)}")
    canvas.restoreState()


def build():
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
                            topMargin=20 * mm, bottomMargin=22 * mm,
                            title="Electricity Basics: Study Notes", author="Demo notes written for this project")
    story = []
    for n, (name, idea, facts, examples) in enumerate(CONCEPTS, start=1):
        if n == 1:
            story += [Paragraph("ELECTRICITY BASICS: STUDY NOTES", label), Spacer(1, 3)]
        story += [Paragraph(f"CONCEPT {n} OF {len(CONCEPTS)}", label), Paragraph(name, title),
                  Paragraph("Key idea", head), Paragraph(idea, body),
                  Paragraph("Facts to know", head)]
        story += [Paragraph(f, fact, bulletText=f"{i}.") for i, f in enumerate(facts, start=1)]
        story.append(Paragraph("Worked examples" if len(examples) > 1 else "Worked example", head))
        box = Table([[Paragraph(e, body)] for e in examples], colWidths=[doc.width])
        box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BOX), ("LEFTPADDING", (0, 0), (-1, -1), 9),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 8),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        story.append(box)
        if n < len(CONCEPTS):
            story.append(PageBreak())
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
