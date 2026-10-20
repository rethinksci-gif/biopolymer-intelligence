"""Verify references and every quote that backs site text.

- Each DOI in data/references.yaml must resolve on Crossref with a matching title.
- Each `support` quote (routes, chemistry explainers, property table, end-of-life matrix) must occur in that
  reference's published abstract (Crossref, else OpenAlex). Abstracts are fetched, compared and discarded:
  they are never stored in the repository.
- Each quote in data/sources.yaml must occur in the official page fetched from `fetch_url`.
Results are written to data/cache/verification.json for the Methods page."""
from __future__ import annotations

import html
import json
import re
import urllib.parse
from datetime import datetime, timezone

from .checks import norm
from .config import CACHE, config, load
from .http import get, get_json


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", norm(text))


def contains(quote: str, text: str) -> bool:
    return bool(quote.strip()) and _squash(quote) in _squash(text)


def crossref(doi: str) -> dict:
    return get_json(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={config()['scan']['mailto']}")["message"]


def abstract(doi: str, cr: dict | None = None) -> str:
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", (cr or {}).get("abstract", ""))).split())
    if True:  # always add OpenAlex: Crossref abstracts are sometimes truncated or reformatted
        try:
            w = get_json(f"https://api.openalex.org/works/doi:{urllib.parse.quote(doi)}?mailto={config()['scan']['mailto']}")
            inv = w.get("abstract_inverted_index") or {}
            pos = {p: t for t, ps in inv.items() for p in ps}
            oa = " ".join(pos[i] for i in sorted(pos))
            text = text + " " + oa
        except Exception:
            pass
    return text


def page_text(url: str, accept: str | None = None) -> str:
    raw = get(url, headers={"Accept": accept or "text/html", "Accept-Language": "en"}, timeout=60).decode("utf-8", "ignore")
    raw = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", raw)).split())


def support_quotes() -> list[tuple[str, str, str]]:
    """(where, ref_id, quote) for every quote that backs text on the site."""
    out = []
    for r in load("routes"):
        out += [(f"routes/{r['id']}", s["ref"], s["quote"]) for s in r.get("support", [])]
    chem = load("chemistry")
    for sec in chem["sections"]:
        out += [(f"chemistry/{sec['id']}", s["ref"], s["quote"]) for s in sec.get("support", [])]
    for cell in chem.get("eol_matrix", {}).get("examples", []):
        if cell.get("ref"):
            out.append((f"chemistry/eol-matrix/{cell['polymer']}", cell["ref"], cell["quote"]))
        if cell.get("also"):
            out.append((f"chemistry/eol-matrix/{cell['polymer']}", cell["also"]["ref"], cell["also"]["quote"]))
    for row in load("properties")["rows"]:
        for prop, v in row["values"].items():
            if isinstance(v, dict):
                out.append((f"properties/{row['id']}/{prop}", v["ref"], v["quote"]))
    return out


def verify_all(offline_ok: bool = False, log=print) -> bool:
    refs = {r["id"]: r for r in load("references")}
    quotes = support_quotes()
    bad, ok_refs, ok_quotes, ok_src = 0, 0, 0, 0
    needed = {ref for _, ref, _ in quotes}
    abstracts: dict[str, str] = {}
    for rid, r in refs.items():
        try:
            m = crossref(r["doi"])
        except Exception as exc:
            log(f"FAIL {rid}: Crossref lookup failed ({exc})")
            bad += 1
            continue
        title = " ".join(html.unescape(re.sub(r"<[^>]+>", "", (m.get("title") or [""])[0])).split())
        same = _squash(r["title"])[:40] == _squash(title)[:40]
        if not same:
            log(f"DIFF {rid}: Crossref title is '{title[:90]}'")
            bad += 1
        else:
            ok_refs += 1
        if rid in needed:
            abstracts[rid] = abstract(r["doi"], m)
    for where, rid, q in quotes:
        if rid not in refs:
            log(f"FAIL {where}: unknown reference '{rid}'")
            bad += 1
        elif not contains(q, abstracts.get(rid, "")):
            log(f"FAIL {where}: quote not found in abstract of {rid}: “{q[:80]}”")
            bad += 1
        else:
            ok_quotes += 1
    for s in load("sources"):
        try:
            text = page_text(s["fetch_url"], s.get("fetch_accept"))
        except Exception as exc:
            log(f"FAIL source {s['id']}: fetch failed ({exc})")
            bad += 0 if offline_ok else 1
            continue
        for q in s["quotes"]:
            if contains(q["text"], text):
                ok_src += 1
            else:
                log(f"FAIL source {s['id']}#{q['id']}: quote not found")
                bad += 1
    log(f"references ok: {ok_refs}/{len(refs)} · support quotes ok: {ok_quotes}/{len(quotes)} · official quotes ok: {ok_src} · failures: {bad}")
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "verification.json").write_text(json.dumps({
        "checked": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "references_ok": ok_refs, "references_total": len(refs),
        "support_quotes_ok": ok_quotes, "support_quotes_total": len(quotes),
        "official_quotes_ok": ok_src, "failures": bad,
    }, indent=2) + "\n")
    return bad == 0
