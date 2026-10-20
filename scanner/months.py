"""Monthly reporting windows. The default window is the previous calendar month."""
from __future__ import annotations

import calendar
import re
from datetime import date


def window(month: str) -> tuple[date, date]:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise ValueError("Expected YYYY-MM")
    y, m = int(month[:4]), int(month[5:])
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def previous(today: date | None = None) -> str:
    today = today or date.today()
    y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return f"{y}-{m:02d}"


def label(month: str) -> str:
    return window(month)[0].strftime("%B %Y")
