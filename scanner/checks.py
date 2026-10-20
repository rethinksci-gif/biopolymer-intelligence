"""Code-side evidence rules shared by triage, development validation and newsletter drafting.
The LLM never produces facts on its own: these functions decide what may be shown."""
from __future__ import annotations

import re

_NUM = re.compile(r"(?<![\w.,])[-+−]?\d+(?:[.,]\d+)*(?![\w])")


def norm(text: str) -> str:
    """Whitespace-normalised, case-folded text with typographic quotes and dashes unified."""
    table = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                           "‐": "-", "‑": "-", "−": "-", " ": " "})
    return " ".join(text.translate(table).split()).casefold()


def quote_in(quote: str, source: str) -> bool:
    return bool(quote.strip()) and norm(quote) in norm(source)


def numbers(text: str) -> list[str]:
    """Numeric tokens, e.g. '12', '3.4', '1,000'. Years inside words or dates are separate tokens."""
    return [m.group(0).lstrip("+").replace("−", "-") for m in _NUM.finditer(text)]


def number_in(num: str, text: str) -> bool:
    """True if `num` occurs in `text` as a whole number (so '12' does not match inside '2012' or '12.5')."""
    n = re.escape(num.lstrip("-"))
    return re.search(rf"(?<![\d.,]){n}(?![\d]|[.,]\d)", text.replace("−", "-")) is not None


def unsupported_numbers(claim: str, quote: str) -> list[str]:
    return [n for n in numbers(claim) if not number_in(n, quote)]
