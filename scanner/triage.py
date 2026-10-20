"""Batch triage with DeepSeek flash. Code, not the model, decides what is shown:
quotes must occur verbatim in the record, ids must be defined, numbers in a summary must be in the quote,
records dated after the cutoff are rejected, and low-relevance leads are hidden."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .checks import quote_in, unsupported_numbers
from .config import PROMPTS, config, llm_config, triage_model
from .llm import LLM, BudgetExceeded, LLMError

NOVELTY = ("new-chemistry", "new-route", "new-formulation-or-application", "scale-or-supply")


class Judgement(BaseModel):
    id: str
    route: str
    novelty_type: str = "new-formulation-or-application"
    relevance: float = Field(ge=0, le=1)
    signal_type: Literal["research", "scale-up", "supply", "policy", "market", "other"] = "other"
    region: str = "not stated"
    summary: str = ""
    quote: str = ""
    quote_location: Literal["title", "abstract"] = "abstract"


class Batch(BaseModel):
    items: list[Judgement]


def prompt_version() -> str:
    m = re.search(r"version:\s*(\S+)", (PROMPTS / "triage.md").read_text())
    return m.group(1) if m else "?"


def system_prompt(routes: list[dict]) -> str:
    listing = "\n".join(f"- {r['id']}: {r['name']} — {r['scope']}" for r in routes)
    return (PROMPTS / "triage.md").read_text().replace("{{routes}}", listing)


def apply(record: dict, j: Judgement, route_ids: set[str], cutoff: str, run_id: str = "", model: str = "") -> dict:
    """Merge a model judgement into a record, enforcing the code-side checks."""
    where = record["title"] if j.quote_location == "title" else record.get("abstract", "")
    quote_ok = quote_in(j.quote, where) or quote_in(j.quote, record["title"] + " " + record.get("abstract", ""))
    location = j.quote_location if quote_in(j.quote, where) else ("title" if quote_in(j.quote, record["title"]) else "abstract")
    route = j.route if j.route in route_ids else "none"
    novelty = j.novelty_type if j.novelty_type in NOVELTY else None
    flags = []
    if j.quote and not quote_ok:
        flags.append("quote-not-in-source")
    bad_numbers = unsupported_numbers(j.summary, j.quote) if quote_ok else []
    if bad_numbers:
        flags.append("number-not-in-quote")
    if not record.get("abstract"):
        flags.append("title-only")
    if j.route not in route_ids and j.route != "none":
        flags.append("unknown-route")
    if novelty is None:
        flags.append("unknown-novelty-type")
    after_cutoff = record["published_date"] > cutoff
    if after_cutoff:
        flags.append("after-cutoff")
    summary_ok = quote_ok and not bad_numbers
    shown = (route != "none" and novelty is not None and summary_ok and not after_cutoff
             and j.relevance >= config()["scan"]["min_relevance"])
    return {
        **record,
        "route": route,
        "novelty_type": novelty or "unclassified",
        "relevance": round(j.relevance, 2),
        "signal_type": j.signal_type,
        "region": j.region[:60] or "not stated",
        "summary": j.summary[:300] if summary_ok else "",
        "quote": j.quote if quote_ok else "",
        "quote_location": location if quote_ok else None,
        "flags": flags,
        "hidden": not shown,
        "triaged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model, "run_id": run_id, "prompt_version": prompt_version(),
    }


def triage(records: list[dict], routes: list[dict], llm: LLM, cutoff: str, run_id: str, log=print) -> list[dict]:
    route_ids = {r["id"] for r in routes}
    system = system_prompt(routes)
    size = llm_config()["batch_size"]
    model = triage_model()
    out = []
    for i in range(0, len(records), size):
        batch = records[i : i + size]
        payload = [{"id": r["id"], "title": r["title"], "abstract": r.get("abstract", "")[:2500], "venue": r["venue"],
                    "date": r["published_date"], "source_type": r["source_type"], "language": r.get("language", "en")} for r in batch]
        try:
            result = llm.json_call(model, system, json.dumps(payload, ensure_ascii=False), Batch, max_tokens=320 * len(batch))
        except BudgetExceeded as exc:
            log(f"  ! {exc}; {len(records) - i} records left untriaged")
            out.extend({**r, "route": "untriaged", "hidden": True, "flags": ["budget"]} for r in records[i:])
            break
        except LLMError as exc:
            log(f"  ! batch {i // size}: {exc}")
            out.extend({**r, "route": "untriaged", "hidden": True, "flags": ["llm-error"]} for r in batch)
            continue
        by_id = {j.id: j for j in result.items}
        for r in batch:
            j = by_id.get(r["id"])
            out.append(apply(r, j, route_ids, cutoff, run_id, model) if j else {**r, "route": "untriaged", "hidden": True, "flags": ["missing-judgement"]})
        log(f"  triaged {min(i + size, len(records))}/{len(records)}")
    return out
