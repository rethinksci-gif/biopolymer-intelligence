"""CLI: python -m scanner {scan,structures,verify-refs,validate,newsletter}"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import date, datetime, timezone

from .config import CACHE, DATA, load, triage_model, max_calls


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def load_gate() -> str:
    from .config import config

    return "|".join(config()["scan"]["keyword_gate"])


def cmd_scan(args):
    from .llm import LLM, LLMError, have_key
    from .months import previous, window
    from .sources import discover
    from .triage import prompt_version, triage

    month = args.month or previous()
    start, end = window(month)
    today = date.today()
    cutoff = min(end, today)
    run_id = f"{month}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
    started = _now()
    routes = load("routes")
    print(f"Run {run_id}: scanning {month} ({start} to {cutoff})")

    llm, triage_on, triage_note = None, have_key(), None
    if triage_on:
        llm = LLM(budget=args.max_calls)
        try:
            llm.check_models(triage_model())
        except LLMError as exc:
            print(f"::error::{exc}")
            sys.exit(2)
    else:
        triage_note = "DEEPSEEK_API_KEY not set: discovery ran, triage skipped (site shows 'triage pending')."
        print(f"::warning::{triage_note}")

    found, errors = discover(routes, start, cutoff)
    path = DATA / "leads" / f"{month}.json"
    previous_file = _read(path, {"leads": []})
    prev = {c["id"]: c for c in previous_file["leads"]}
    cache_path = CACHE / "triaged.json"
    triaged_hashes = set(_read(cache_path, []))
    # Cross-month dedupe: anything already triaged in any month is never re-sent.
    fresh = [r for r in found if r["hash"] not in triaged_hashes and prev.get(r["id"], {}).get("route", "untriaged") == "untriaged"]
    gate = re.compile(load_gate(), re.I)
    off_topic = [r for r in fresh if not gate.search(r["title"] + " " + r.get("abstract", ""))]
    fresh = [r for r in fresh if r not in off_topic]
    # Spend the budget on the most promising records first: focus routes, then journal/preprint, then news.
    focus = {r["id"] for r in routes if r.get("focus")}
    fresh.sort(key=lambda r: (not (set(r["seed_routes"]) & focus), r["source_type"] == "news", r["published_date"]))
    for r in off_topic:  # code-side keyword gate: never sent to the LLM, kept hidden with a flag
        prev[r["id"]] = {**r, "route": "none", "hidden": True, "flags": ["keyword-gate"], "relevance": 0}
        triaged_hashes.add(r["hash"])
    for r in found:  # keep untriaged records so a later run (with a key or more budget) can triage them
        prev.setdefault(r["id"], {**r, "route": "untriaged", "hidden": True, "flags": ["triage-pending"]})
    print(f"{len(found)} discovered, {len(off_topic)} failed the keyword gate, {len(fresh)} new to triage")

    judged = triage(fresh, routes, llm, cutoff.isoformat(), run_id) if (triage_on and fresh) else []
    for j in judged:
        prev[j["id"]] = j
        if j.get("route") != "untriaged":
            triaged_hashes.add(j["hash"])
    leads = sorted(prev.values(), key=lambda c: (-c.get("relevance", 0), c["published_date"]))
    for c in leads:  # publisher abstracts are only needed until a record is triaged; never republish them
        if c.get("route") != "untriaged":
            c.pop("abstract", None)
    pending = sum(c.get("route") == "untriaged" for c in leads)
    _write(path, {
        "month": month, "window": [str(start), str(end)], "scanned_through": str(cutoff),
        "status": "complete" if cutoff >= end else "in-progress", "updated": _now(),
        "triage_model": triage_model() if triage_on else None, "prompt_version": prompt_version(),
        "triage_pending": pending, "discovery_errors": len(errors),
        "note": "Machine-triaged discovery leads. Not verified evidence: each needs a primary-source evidence check before it can enter a newsletter.",
        "leads": leads,
    })
    _write(cache_path, sorted(triaged_hashes))
    shown = sum(not c.get("hidden", True) for c in leads)
    run = {
        "run_id": run_id, "month": month, "started": started, "finished": _now(), "scanned_through": str(cutoff),
        "triage": "ran" if triage_on else "skipped (no key)", "triage_note": triage_note,
        "triage_model": triage_model() if triage_on else None, "prompt_version": prompt_version(),
        "budget": llm.budget if llm else max_calls(), "llm_calls": llm.calls if llm else 0,
        "usage": llm.usage if llm else {"prompt_tokens": 0, "completion_tokens": 0},
        "by_model": llm.by_model if llm else {}, "cost_usd": llm.cost_usd() if llm else None,
        "discovered": len(found), "keyword_gate_rejected": len(off_topic), "sent_to_llm": len(fresh) if triage_on else 0, "shown": shown,
        "triage_pending": pending, "discovery_errors": errors[:50],
    }
    runs_path = DATA / "runs" / f"{month}.json"
    runs = _read(runs_path, {"month": month, "runs": []})
    runs["runs"].append(run)
    _write(runs_path, runs)
    print(f"{shown} shown / {len(leads)} total -> {path}; calls={run['llm_calls']} usage={run['usage']} pending={pending}")


def cmd_recheck_dates(args):
    """Look up each DOI lead's first availability on Crossref (once) and hide, with a `pre-window` flag, any lead
    that was online before the month began."""
    from .http import get_json
    from .months import window
    from .sources import first_available

    start, _ = window(args.month)
    path = DATA / "leads" / f"{args.month}.json"
    doc = _read(path, None)
    if doc is None:
        sys.exit(f"no leads file for {args.month}")
    checked = moved = failed = 0
    for c in doc["leads"]:
        # Every DOI lead is checked once (`first_available` marks it): OpenAlex and Europe PMC can also report
        # an issue date as a day-precision date. Keyword-gated records are never shown, so they are skipped.
        if not c.get("doi") or "first_available" in c or {"pre-window", "keyword-gate"} & set(c.get("flags", [])):
            continue
        try:
            m = get_json("https://api.crossref.org/works/" + c["doi"])["message"]
        except Exception as exc:  # reported, never fatal: the lead keeps its issue date
            failed += 1
            print(f"  ! {c['doi']}: {exc}")
            continue
        checked += 1
        first, exact = first_available(m) or (c["published_date"], False)
        c["first_available"] = first
        if exact and c.get("date_precision") == "month":
            c["date_precision"] = "day"
        if first < start.isoformat():
            c["hidden"] = True
            c["flags"] = sorted(set(c.get("flags", [])) | {"pre-window"})
            moved += 1
    doc["triage_pending"] = sum(c.get("route") == "untriaged" and "pre-window" not in c.get("flags", []) for c in doc["leads"])
    doc["updated"] = _now()
    _write(path, doc)
    print(f"{args.month}: {checked} DOI leads checked, {moved} online before {start} hidden as pre-window, {failed} lookups failed")


def cmd_structures(args):
    from .structures import StructureError, render, verify

    try:
        if args.verify_only:
            errs = verify(offline=not args.refresh)
            if errs:
                raise StructureError("\n  ".join(errs))
            print("all structures verified")
        else:
            print("rendered:", ", ".join(render(offline=not args.refresh)))
    except StructureError as exc:
        print(f"::error::{exc}")
        sys.exit(1)


def cmd_verify_refs(args):
    from .refs import verify_all

    sys.exit(0 if verify_all(offline_ok=args.allow_offline) else 1)


def cmd_validate(args):
    from .validate import validate_all

    errors = validate_all()
    for e in errors:
        print("::error::" + e)
    print(f"{len(errors)} validation error(s)")
    sys.exit(1 if errors else 0)


def cmd_newsletter(args):
    from .newsletter import build, draft

    if args.action == "draft":
        draft(args.month)
    else:
        sys.exit(0 if build(args.month, pdf=not args.no_pdf) else 1)


def main():
    p = argparse.ArgumentParser(prog="scanner")
    sub = p.add_subparsers(required=True)
    s = sub.add_parser("scan", help="discover and triage leads for a month (default: previous calendar month)")
    s.add_argument("--month")
    s.add_argument("--max-calls", type=int)
    s.set_defaults(fn=cmd_scan)
    rd = sub.add_parser("recheck-dates", help="re-date issue-dated leads by first availability; hide pre-window ones")
    rd.add_argument("month")
    rd.set_defaults(fn=cmd_recheck_dates)
    st = sub.add_parser("structures", help="verify structures against PubChem and render SVGs")
    st.add_argument("--refresh", action="store_true", help="look up CIDs missing from the PubChem cache")
    st.add_argument("--verify-only", action="store_true")
    st.set_defaults(fn=cmd_structures)
    v = sub.add_parser("verify-refs", help="check DOIs on Crossref and every support quote against its source")
    v.add_argument("--allow-offline", action="store_true")
    v.set_defaults(fn=cmd_verify_refs)
    sub.add_parser("validate", help="validate data files against JSON schemas and evidence rules").set_defaults(fn=cmd_validate)
    n = sub.add_parser("newsletter", help="build (HTML+PDF, checks) or draft a monthly issue")
    n.add_argument("action", choices=["build", "draft"])
    n.add_argument("month")
    n.add_argument("--no-pdf", action="store_true")
    n.set_defaults(fn=cmd_newsletter)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
