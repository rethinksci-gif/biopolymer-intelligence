"""Polite HTTP with retries/backoff. Network failures are reported, never hidden."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

UA = "BIOPOLYMER-Intelligence/0.1 (+https://github.com/rethinksci-gif/biopolymer-intelligence; mailto:biopolymer-intelligence@users.noreply.github.com)"


def get(url: str, timeout: int = 40, headers: dict | None = None, tries: int = 4) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == tries - 1:
                raise
        time.sleep(2 ** attempt * 2)
    raise RuntimeError("unreachable")


def get_json(url: str, **kw):
    return json.loads(get(url, **kw))
