# Quick Start Commands

```bash
.venv/bin/pytest -q                                              # all tests (163)
./run.sh                                                         # teacher http://localhost:8501, students http://<lan-ip>:8502/?exam=CODE
.venv/bin/python -m tutor.build_bank demo/Electricity_Basics.pdf --name electricity_llm
.venv/bin/python -m tutor.simulate --n 14 --report               # fake class + dashboard text
.venv/bin/python -m tutor.eval                                   # bank, mastery and judge scores
.venv/bin/python -m tutor.smoke                                  # keys, JSON mode, model list
node claude-token-optimizer/bin/cto.js measure                   # startup token estimate
```
