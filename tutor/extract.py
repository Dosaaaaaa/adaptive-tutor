"""PDF to text, one entry per page (SPEC 5.1 step 0)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .models import Page


class ExtractError(Exception):
    pass


def pdf_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract_pages(path: str | Path) -> list[Page]:
    import pymupdf  # imported here so the rest of the package works without it

    with pymupdf.open(str(path)) as doc:
        pages = [Page(n=i + 1, text=page.get_text("text").strip()) for i, page in enumerate(doc)]
    if not any(len(p.text) > 40 for p in pages):
        raise ExtractError("No text found. This looks like a scanned PDF (OCR is not supported in v1).")
    return pages


def doc_text(pages: list[Page], only: set[int] | None = None) -> str:
    """Document text with [PAGE n] markers, optionally limited to some pages."""
    return "\n\n".join(f"[PAGE {p.n}]\n{p.text}" for p in pages if only is None or p.n in only)
