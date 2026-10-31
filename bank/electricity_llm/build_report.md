# Build report: electricity_llm

- PDF: `Electricity_Basics.pdf` (5 pages)
- Generator: `gemini:gemini-3.6-flash`  Verifier: `groq:openai/gpt-oss-120b`
- Concepts: 5, edges: 5, misconceptions: 15
- Questions generated: 30, kept: 28 (93% passed)
- AI calls (not from cache): {'generator': 13, 'verifier': 32}
- Time: 789 s

## Warnings
- no_misconception_tag: C3-simple-1: no distractor is tagged with a misconception
- no_misconception_tag: C4-simple-1: no distractor is tagged with a misconception

## Questions that failed a check

| question | what happened |
|---|---|
| C1-recall-1 | dropped: leaks another answer or duplicates a question |
| C2-simple-1 | dropped: leaks another answer or duplicates a question |
