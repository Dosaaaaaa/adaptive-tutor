# Common Mistakes

## Top 5 Critical Mistakes

### 1. Leaking an API key
**Symptom**: a key in chat, a log, a commit or a screenshot.
**Fix**: keys only in `.env` (git-ignored). Print model names and OK/FAIL, never values.

### 2. Using the system Python
**Symptom**: missing packages or odd wheel errors. System default is 3.14.
**Fix**: always `.venv/bin/python` (3.12).

### 3. Showing answers during the test
**Symptom**: round 2 measures memory of round 1.
**Fix**: feedback only on the results page after the last round.

### 4. Counting simulated students as real
**Fix**: `is_simulated=1`, label them in every report.

### 5. Hard-coding model names
**Fix**: free-tier model lists change. Set `GEN_MODEL` and `VERIFY_MODEL` via `tutor.smoke`.
