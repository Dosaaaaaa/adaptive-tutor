# Architecture Map

```
tutor/   config quotes models extract mastery rounds db service judge stats   (core)
         llm gates verify build_bank prompts/                                  (PDF to quiz bank)
         simulate eval smoke                                                   (testing, keys)
tutor/   exams scoring jobs   (exam layer: seats, link, scores, background PDF build)
ui/      teacher_app.py + teacher/*.py (private, password), student_app.py (the link)
bank/<name>/  concepts misconceptions questions pages manifest, build_report.md
demo/    Electricity_Basics.pdf, expected.json, make_demo_pdf.py
data/    tutor.db (git-ignored)      tests/   pytest
```
Flow: PDF -> bank -> `service` (student) -> SQLite -> `stats` (teacher).
