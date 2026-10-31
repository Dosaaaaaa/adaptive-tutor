"""Quote matching. Every quote the AI gives must appear word for word in the PDF text (SPEC 5.2)."""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable

_PUNCT = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", " ": " ",
})


def norm(text: str) -> str:
    """NFKC, simple punctuation, lower case, single spaces."""
    t = unicodedata.normalize("NFKC", text or "").translate(_PUNCT).casefold()
    return re.sub(r"\s+", " ", t).strip()


def quote_in(quote: str, text: str) -> bool:
    q = norm(quote)
    return bool(q) and "..." not in q and "…" not in q and q in norm(text)


def find_page(quote: str, pages: Iterable) -> int | None:
    """Page number of the first page holding the quote. Pages need .n and .text."""
    pages = list(pages)
    for p in pages:
        if quote_in(quote, p.text):
            return p.n
    joined = " ".join(p.text for p in pages)
    if quote_in(quote, joined):  # quote runs over a page break: report where it starts
        head = norm(quote)[:40]
        for p in pages:
            if head in norm(p.text):
                return p.n
    return None


def words(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))
