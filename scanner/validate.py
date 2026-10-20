"""Validate data files against JSON schemas and the evidence rules that schemas cannot express.

Evidence rules for checked developments:
- no value without a quote, and every number in a value must appear (as a whole number) in its quote;
- capacity always carries a status; nameplate capacity is never recorded as output;
- no climate reduction is stated across different system boundaries;
- source and event dates must not be after the issue cutoff;
- dedupe by technology + organisation + facility + event across months (repeats need a reason);
- signed issues need a named reviewer and date."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .checks import numbers, number_in
from .config import DATA, SCHEMAS, load
from .months import window

MISSING = {"Not disclosed", "Not reported", "Not assessed", "ND", None, ""}


def _schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMAS / f"{name}.schema.json").read_text()))


def _errs(validator, obj, where: str) -> list[str]:
    return [f"{where}: {'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in validator.iter_errors(obj)]


def _dates(obj):
    return json.loads(json.dumps(obj, default=str))


def facts(obj, path=""):
    """Yield (path, dict) for every object carrying a `value`."""
    if isinstance(obj, dict):
        if "value" in obj:
            yield path, obj
        for k, v in obj.items():
            yield from facts(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from facts(v, f"{path}/{i}")


def check_development(d: dict, cutoff: str) -> list[str]:
    e, where = [], f"developments/{d.get('id')}"
    for path, f in facts(d):
        if f["value"] in MISSING:
            continue
        q = f.get("quote") or ""
        if not q or not f.get("source"):
            e.append(f"{where}{path}: value '{f['value']}' has no quote/source")
            continue
        for n in numbers(str(f["value"])):
            if not number_in(n, q):
                e.append(f"{where}{path}: number {n} not found as a whole number in its quote")
    cap = d.get("capacity") or {}
    if cap.get("value") not in MISSING and not cap.get("status"):
        e.append(f"{where}/capacity: value without status (nameplate capacity must never be shown as output)")
    cl = d.get("climate") or {}
    if cl.get("reduction") and cl.get("comparator_boundary") != cl.get("boundary"):
        e.append(f"{where}/climate: reduction stated across different boundaries")
    for s in d.get("sources", []):
        if s.get("published") and s["published"] > cutoff:
            e.append(f"{where}: source {s['url']} dated {s['published']} is after cutoff {cutoff}")
    for k in ("published_date",):
        if d.get(k) and d[k] > cutoff:
            e.append(f"{where}: {k} {d[k]} is after cutoff {cutoff}")
    if d["review"]["status"] == "signed" and not (d["review"].get("reviewer") and d["review"].get("date")):
        e.append(f"{where}: signed without reviewer name and date")
    return e


def _key(d: dict) -> tuple | None:
    k = d.get("dedupe_key")
    if not k:
        return None
    return tuple(re.sub(r"\W+", "", str(k.get(f, "")).casefold()) for f in ("technology", "organization", "facility", "event"))


def validate_all() -> list[str]:
    errors: list[str] = []
    route_ids = {r["id"] for r in load("routes")}
    ref_ids = {r["id"] for r in load("references")}
    mol_ids = {m["id"] for m in load("structures")}
    src = {s["id"]: {q["id"] for q in s["quotes"]} for s in load("sources")}
    for name in ("routes", "structures", "references"):
        errors += _errs(_schema(name), _dates(load(name)), name)
    for r in load("routes"):
        errors += [f"routes/{r['id']}: unknown ref {x}" for x in r["refs"] if x not in ref_ids]
        errors += [f"routes/{r['id']}: unknown structure {x}" for x in r["structures"] if x not in mol_ids]
        errors += [f"routes/{r['id']}: support ref {s['ref']} not in refs list" for s in r.get("support", []) if s["ref"] not in r["refs"]]
    challenge_ids = {c["id"] for c in load("challenges")}
    for r in load("routes"):
        errors += [f"routes/{r['id']}: unknown challenge {x}" for x in r["challenge_links"] if x not in challenge_ids]
    for m in load("structures"):
        errors += [f"structures/{m['id']}: unknown route {x}" for x in m["routes"] if x not in route_ids]
        if m["ref"] not in ref_ids:
            errors.append(f"structures/{m['id']}: unknown ref {m['ref']}")
    chem = load("chemistry")
    for sec in chem["sections"]:
        for b in sec["blocks"]:
            errors += [f"chemistry/{sec['id']}: unknown ref {x}" for x in b.get("refs", []) if x not in ref_ids]
            errors += [f"chemistry/{sec['id']}: unknown structure {x}" for x in b.get("structures", []) if x not in mol_ids]
            for s in b.get("sources", []):
                sid, _, qid = s.partition("#")
                if sid not in src or (qid and qid not in src[sid]):
                    errors.append(f"chemistry/{sec['id']}: unknown source quote {s}")
            if not b.get("refs") and not b.get("sources"):
                errors.append(f"chemistry/{sec['id']}/{b['heading']}: paragraph without reference or source")
    for c in load("challenges"):
        errors += [f"challenges/{c['id']}: unknown ref {x}" for x in c.get("refs", []) if x not in ref_ids]
        for s in c.get("sources", []):
            if s.partition("#")[0] not in src:
                errors.append(f"challenges/{c['id']}: unknown source {s}")
    for row in load("properties")["rows"]:
        for prop, v in row["values"].items():
            if v == "ND":
                continue
            if v["ref"] not in ref_ids:
                errors.append(f"properties/{row['id']}/{prop}: unknown ref")
            for n in numbers(v["value"]):
                if not number_in(n, v["quote"]):
                    errors.append(f"properties/{row['id']}/{prop}: value {v['value']} not in quote")

    lead_schema = _schema("lead")
    for path in sorted((DATA / "leads").glob("*.json")):
        f = json.loads(path.read_text())
        for c in f["leads"]:
            errors += _errs(lead_schema, c, f"leads/{path.stem}/{c['id']}")
            if c.get("route") != "untriaged" and "abstract" in c:
                errors.append(f"leads/{path.stem}/{c['id']}: triaged record still carries a publisher abstract")
            if not c.get("hidden") and c["published_date"] > f["scanned_through"]:
                errors.append(f"leads/{path.stem}/{c['id']}: shown lead dated after the scan cutoff")

    dev_schema = _schema("development")
    seen: dict[tuple, str] = {}
    for path in sorted((DATA / "developments").glob("*.yaml")):
        month = path.stem
        devs = _dates(yaml.safe_load(path.read_text()) or [])
        cutoff = window(month)[1].isoformat()
        for d in devs:
            errors += _errs(dev_schema, d, f"developments/{month}/{d.get('id')}")
            errors += check_development(d, cutoff)
            k = _key(d)
            if k and k in seen and not d.get("repeat_reason"):
                errors.append(f"developments/{month}/{d['id']}: duplicates {seen[k]} without repeat_reason (new-milestone/correction/reversal)")
            if k:
                seen.setdefault(k, f"{month}/{d['id']}")

    nl_schema = _schema("newsletter")
    for path in sorted((DATA / "newsletter").glob("*.yaml")):
        n = _dates(yaml.safe_load(path.read_text()))
        errors += _errs(nl_schema, n, f"newsletter/{path.stem}")
        if n["status"] == "signed" and not (n["review"].get("reviewer") and n["review"].get("date")):
            errors.append(f"newsletter/{path.stem}: signed without reviewer name and date")
        devs = {d["id"]: d for d in (yaml.safe_load((DATA / "developments" / f"{path.stem}.yaml").read_text()) or [])} \
            if (DATA / "developments" / f"{path.stem}.yaml").exists() else {}
        for card in n.get("cards") or []:
            if card["development"] not in devs:
                errors.append(f"newsletter/{path.stem}: card cites unknown development {card['development']}")
        if n["status"] in ("evidence-checked", "signed"):
            for card in n.get("cards") or []:
                d = devs.get(card["development"])
                if d and d["review"]["status"] == "draft":
                    errors.append(f"newsletter/{path.stem}: issue is {n['status']} but development {d['id']} is still draft")
    return errors
