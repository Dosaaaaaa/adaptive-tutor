"""Turns an uploaded PDF into a quiz bank in the background, and reports progress (the SPEC 5 pipeline, run from the UI).

The build can take 10 to 15 minutes with the free AI models, so it runs as its own process that survives a page reload
or an app restart. The exam stays in status 'building' until the bank is written.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
from pathlib import Path

from . import config, exams, llm
from .models import FILES


class UploadError(Exception):
    """The file cannot be used. The message is safe to show on screen."""


def validate_pdf(data: bytes) -> dict:
    """Check an uploaded file before anything is saved or sent to an AI. Returns its page count and hash."""
    if not data:
        raise UploadError("The file is empty.")
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise UploadError(f"The file is larger than {config.MAX_UPLOAD_MB} MB.")
    if not data.lstrip()[:5] == b"%PDF-":
        raise UploadError("This does not look like a PDF file.")
    try:
        import pymupdf

        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass:
                raise UploadError("This PDF is password-protected. Please remove the password and upload it again.")
            pages, chars = doc.page_count, sum(len(p.get_text()) for p in doc)
    except UploadError:
        raise
    except Exception:
        raise UploadError("The PDF could not be read. It may be damaged.")
    if pages > config.MAX_PDF_PAGES:
        raise UploadError(f"The PDF has {pages} pages. The limit is {config.MAX_PDF_PAGES}.")
    if chars < 200:
        raise UploadError("No readable text was found. Scanned PDFs are not supported yet (there is no OCR).")
    return {"pages": pages, "sha256": hashlib.sha256(data).hexdigest()}


def reusable_bank(sha256: str, max_concepts: int) -> str | None:
    """A quiz bank already built from exactly this file with the same settings: no need to build it again."""
    found = []
    for manifest_path in config.BANK_DIR.glob("*/manifest.json"):
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        folder = manifest_path.parent
        if (m.get("pdf_sha256") == sha256 and m.get("max_concepts") == max_concepts
                and all((folder / f).exists() for f in FILES)):
            found.append((0 if m.get("ai_checks") else 1, folder.name))   # prefer one the AI checks have passed
    return sorted(found)[0][1] if found else None


def ai_config_problem() -> str | None:
    """Why a new PDF cannot be built right now (missing keys or models), or None when it can."""
    try:
        llm.assert_independent(llm.from_env("generator"), llm.from_env("verifier"))
    except llm.ConfigError as exc:
        return str(exc)
    return None


def building_now(conn) -> dict | None:
    """The exam whose quiz is being built, if any. Free AI limits are shared, so only one build runs at a time."""
    for e in exams.list_exams(conn):
        if e["status"] == "building":
            refreshed = refresh(conn, e)
            if refreshed["status"] == "building":
                return refreshed
    return None


def start_build(conn, code: str, data: bytes, *, bank_name: str, max_concepts: int, command: list[str] | None = None) -> int:
    """Save the PDF privately and start the build as a separate process. Returns its process id."""
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    config.BUILD_DIR.mkdir(parents=True, exist_ok=True)
    pdf = config.UPLOAD_DIR / f"{code}.pdf"
    pdf.write_bytes(data)
    os.chmod(pdf, 0o600)
    log = config.BUILD_DIR / f"{code}.log"
    cmd = command or [sys.executable, "-W", "ignore", "-u", "-m", "tutor.build_bank", str(pdf), "--name", bank_name,
                      "--max-concepts", str(max_concepts)]
    with open(log, "wb") as fh:
        proc = subprocess.Popen(cmd, cwd=config.ROOT, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True)
    threading.Thread(target=proc.wait, daemon=True).start()      # reap it, so it never lingers as a zombie
    ticks = _start_ticks(proc.pid)
    if ticks:
        (config.BUILD_DIR / f"{code}.proc").write_text(ticks)     # which exact process this is: a pid can be reused
    exams.update_exam(conn, code, pid=proc.pid, log_path=str(log), bank_name=bank_name, status="building")
    return proc.pid


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists():
        try:
            return stat.read_text().rsplit(")", 1)[1].split()[0] not in ("Z", "X")
        except (OSError, IndexError):
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _start_ticks(pid: int) -> str | None:
    """When the process started (clock ticks since boot). Together with the pid this names one exact process."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def _is_the_build(exam: dict) -> bool:
    """The stored pid is alive AND is still the process we started (not a different one that reused the pid)."""
    pid = exam.get("pid")
    if not pid or not _alive(pid):
        return False
    marker = config.BUILD_DIR / f"{exam['code']}.proc"
    return marker.read_text().strip() == (_start_ticks(pid) or "") if marker.exists() else True


def _safe_to_kill(exam: dict) -> bool:
    """Only ever signal a process we are sure is our build."""
    pid = exam.get("pid")
    if not pid or not _is_the_build(exam):
        return False
    if (config.BUILD_DIR / f"{exam['code']}.proc").exists():
        return True
    try:                                        # an older build without a marker: it must look exactly like one of ours
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        return "tutor.build_bank" in cmd and os.getpgid(pid) == pid
    except OSError:
        return False


def cancel_build(conn, exam: dict) -> None:
    """Stop a build that is running. The exam is marked failed, and Try again can resume it from where it was."""
    if exam["status"] != "building":
        raise UploadError("This quiz is not being built.")
    if _safe_to_kill(exam):
        try:
            os.killpg(exam["pid"], signal.SIGTERM)       # the build leads its own process group (start_new_session)
        except ProcessLookupError:
            pass
    exams.update_exam(conn, exam["code"], status="failed",
                      error="You stopped this build. Press Try again to start it again: the steps already finished are "
                            "remembered, so it carries on quickly.")


def parse_progress(log_text: str) -> tuple[float, str]:
    """A rough progress bar from the lines the build prints."""
    lines = [l.strip() for l in log_text.splitlines()]
    if any(l.startswith("wrote ") for l in lines):
        return 1.0, "Done."
    total = next((int(m.group(1)) for l in lines if (m := re.match(r"\[1\] (\d+) concepts", l))), 0)
    done = sum(l.startswith("[2-3]") for l in lines)
    if any(l.startswith("[4]") for l in lines):
        return 0.97, "Almost done."
    if total and done >= total:
        return 0.65, "Checking every question with a second AI. This is the slowest step: several minutes."
    if total:
        return 0.15 + 0.5 * done / total, f"Writing questions: concept {min(done + 1, total)} of {total}."
    if any(l.startswith("[0]") for l in lines):
        return 0.05, "Reading the PDF and finding its concepts."
    return 0.02, "Starting."


def refresh(conn, exam: dict) -> dict:
    """Look at a building exam and move it to 'ready' or 'failed' when its process has finished."""
    exam = dict(exam)
    log_text = ""
    if exam.get("log_path") and Path(exam["log_path"]).exists():
        log_text = Path(exam["log_path"]).read_text(encoding="utf-8", errors="replace")
    exam["progress"], exam["message"] = parse_progress(log_text)
    if exam["status"] != "building":
        return exam
    bank_dir = config.BANK_DIR / (exam["bank_name"] or "-")
    if all((bank_dir / f).exists() for f in FILES) and any(l.startswith("wrote ") for l in log_text.splitlines()):
        exams.update_exam(conn, exam["code"], status="ready", error=None)
        exam.update(status="ready", progress=1.0, message="Done.")
    elif not _is_the_build(exam):
        lines = [l for l in log_text.splitlines() if l.strip()]
        if any("Build stopped" in l or "Traceback" in l or "Error" in l for l in lines):
            why = " ".join(lines[-4:])[:400]                      # the build said what went wrong
        else:                                                    # it just ended: killed, restarted, or the computer slept
            why = ("The build stopped before it finished (the app may have been restarted, or the computer went to sleep). "
                   "Press Try again: the steps already finished are remembered, so it carries on quickly.")
        exams.update_exam(conn, exam["code"], status="failed", error=why)
        exam.update(status="failed", error=why)
    return exam


def forget_files(code: str) -> None:
    """Remove the uploaded PDF and the build log of a deleted exam. The quiz bank stays: another exam may reuse it."""
    for path in (config.UPLOAD_DIR / f"{code}.pdf", config.BUILD_DIR / f"{code}.log", config.BUILD_DIR / f"{code}.proc"):
        path.unlink(missing_ok=True)


def create_exam_from_pdf(conn, title: str, data: bytes, filename: str, max_students: int, max_concepts: int,
                         *, command: list[str] | None = None) -> dict:
    """Everything behind the upload button. Returns the exam, with `reused` set when no new build was needed."""
    info = validate_pdf(data)
    existing = reusable_bank(info["sha256"], max_concepts)
    if existing:    # the same file was built before with the same settings: ready at once, no AI calls
        exam = exams.create_exam(conn, title, max_students, bank_name=existing, pdf_name=filename,
                                 max_concepts=max_concepts, status="ready")
        return {**exam, "reused": True}
    problem = ai_config_problem()
    if problem:
        raise UploadError(f"The quiz cannot be built yet. {problem}")
    busy = building_now(conn)
    if busy:
        raise UploadError(f"Another quiz (“{busy['title']}”) is still being built. The free AI limits are shared, "
                          "so please wait until it is ready, or stop it with “Stop building” on that exam below.")
    exam = exams.create_exam(conn, title, max_students, pdf_name=filename, max_concepts=max_concepts, status="building")
    try:
        start_build(conn, exam["code"], data, bank_name=f"exam_{exam['code'].lower()}", max_concepts=max_concepts,
                    command=command)
    except OSError as exc:
        exams.update_exam(conn, exam["code"], status="failed", error=f"Could not start the build: {exc}")
        raise UploadError("The build could not be started. Please try again.") from exc
    return {**exams.get_exam(conn, exam["code"]), "reused": False}


def retry_build(conn, exam: dict, *, command: list[str] | None = None) -> None:
    """Run a failed build again from the PDF saved at upload time. Answers already received are cached, so it is cheaper."""
    pdf = config.UPLOAD_DIR / f"{exam['code']}.pdf"
    if not pdf.exists():
        raise UploadError("The uploaded PDF is no longer on this computer. Please create the exam again.")
    if building_now(conn):
        raise UploadError("Another quiz is still being built. Please wait until it is ready.")
    start_build(conn, exam["code"], pdf.read_bytes(), bank_name=exam["bank_name"] or f"exam_{exam['code'].lower()}",
                max_concepts=exam["max_concepts"] or config.MAX_CONCEPTS, command=command)
