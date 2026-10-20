"""Monthly newsletter: build (HTML + PDF + checks) and optional drafting from verified evidence.

Rules (content brief): generated only from checked developments; 350-500 words including captions and
references; the rendered PDF is at most 2 A4 pages (checked with pypdf); body text >= 10.5 pt (reduce item
count before font size); lead cards 45-70 words with a 5-9 word headline and Change / Implication / Gap;
every number in drafted text must exist in the evidence record. Issues are drafts until a named reviewer
signs them. Nothing is emailed or posted."""
from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .checks import number_in, numbers
from .config import DATA, ROOT, config, draft_model, llm_config, load
from .months import label

PUBLIC = ROOT / "site" / "public" / "newsletter"
SVG_DIR = ROOT / "site" / "src" / "generated" / "structures"
BODY_PT = 10.5
NAME = "BIOPOLYMER_MONTHLY"


def _e(s) -> str:
    return html.escape(str(s or ""))


def _yaml(path: Path, default):
    return json.loads(json.dumps(yaml.safe_load(path.read_text()), default=str)) if path.exists() else default


def issue_paths(month: str) -> dict:
    return {"html": PUBLIC / f"{NAME}_{month}.html", "pdf": PUBLIC / f"{NAME}_{month}.pdf", "png": PUBLIC / f"{NAME}_{month}-p1.png",
            "build": DATA / "newsletter" / f"{month}.build.json"}


def word_count(text: str) -> int:
    return len(re.findall(r"[\w’'-]+", text))


def _structure(mol_id: str, caption: str) -> str:
    svg = (SVG_DIR / f"{mol_id}.svg").read_text() if (SVG_DIR / f"{mol_id}.svg").exists() else ""
    return f'<figure class="viz">{svg}<figcaption>{_e(caption)}</figcaption></figure>'


def render_html(month: str, issue: dict, devs: dict, leads: dict) -> str:
    mols = {m["id"]: m for m in load("structures")}
    routes = {r["id"]: r for r in load("routes")}
    site = config()["site"]
    status = issue["status"]
    stamp = {"draft": "DRAFT · not signed · item status varies", "evidence-checked": "Evidence-checked · not yet signed",
             "signed": f"Signed by {issue['review'].get('reviewer')} on {issue['review'].get('date')}"}[status]
    refs: list[str] = []

    def ref(url: str, text: str) -> int:
        refs.append(f'<li><a href="{_e(url)}">{_e(text)}</a></li>')
        return len(refs)

    cards = []
    for c in issue.get("cards") or []:
        d = devs[c["development"]]
        n = ref(d["sources"][0]["url"], d["title"])
        viz = _structure(c["visual"], mols[c["visual"]]["name"]) if c.get("visual") else \
            f'<div class="placeholder"><b>Visual placeholder</b><br>Drawing brief: {_e(c.get("visual_brief", ""))}</div>'
        cards.append(f'<article class="card">{viz}<div><h3>{_e(c["headline"])}</h3>'
                     f'<p><b>Change</b> {_e(c["change"])} <sup>{n}</sup></p><p><b>Implication</b> {_e(c["implication"])}</p>'
                     f'<p><b>Gap</b> {_e(c["gap"])}</p></div></article>')
    short = []
    for s in issue.get("shortlist") or []:
        lead = leads.get(s["lead_id"])
        if not lead:
            continue
        r = routes.get(lead["route"], {})
        n = ref(lead["url"], lead["title"])
        ru = next((m for m in r.get("structures", []) if mols[m]["role_label"] == "repeat unit"), (r.get("structures") or [None])[0])
        viz = _structure(ru, f"{mols[ru]['name']} - route reference structure, not specific to this lead") if ru else ""
        short.append(f'<article class="card cand">{viz}<div><p class="tag">Candidate for evidence check · {_e(r.get("name", lead["route"]))} · '
                     f'{_e(lead.get("novelty_type", ""))}</p><h3>{_e(lead["title"])}</h3>'
                     f'<p class="quote">“{_e(lead["quote"])}” <sup>{n}</sup></p>'
                     f'<p><b>Evidence record</b> empty - Change / Implication / Gap will be written only after the primary source is checked.</p></div></article>')
    comp = ""
    if issue.get("cards"):
        rows = []
        for c in issue["cards"]:
            d = devs[c["development"]]
            g = lambda k, f="value": (d.get(k) or {}).get(f) if isinstance(d.get(k), dict) else d.get(k)
            cells = [d.get("polymer_family") or d["title"], d.get("production_site") or "ND", d.get("demonstrated_stage") or "ND",
                     g("trl") or "ND", " ".join(x for x in [str(g("capacity") or "ND"), str(g("capacity", "status") or "")] if x),
                     " ".join(x for x in [str(g("cost") or "ND"), str(g("cost", "basis") or "")] if x),
                     " ".join(x for x in [str(g("climate") or "ND"), str(g("climate", "boundary") or "")] if x)]
            rows.append("<tr>" + "".join(f"<td>{_e(x)}</td>" for x in cells) + "</tr>")
        comp = ('<table class="strip"><thead><tr><th scope="col">Entity / polymer</th><th scope="col">Production geography</th><th scope="col">Demonstrated scale</th><th scope="col">TRL</th>'
                '<th scope="col">Capacity / status</th><th scope="col">Cost / basis</th><th scope="col">Climate / boundary</th></tr></thead><tbody>' + "".join(rows) +
                '</tbody></table><p class="fn">ND = not disclosed. Capacity is nameplate unless the status says actual output.</p>')
    notes = "".join(f"<li>{_e(x)}</li>" for x in issue.get("notes") or [])
    watch = "".join(f"<li>{_e(x)}</li>" for x in issue.get("watchlist") or [])
    qs = "".join(f"<li>{_e(x)}</li>" for x in issue.get("questions") or [])
    page1_cards = (cards + short)[:2]
    page2_cards = (cards + short)[2:3]
    what = issue.get("what_changed") or "Not yet written: no development has passed the evidence check for this month."
    return f"""<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8"><title>BIOPOLYMER Monthly · {_e(label(month))}</title>
<style>
@page {{ size: A4; margin: 14mm 14mm 12mm; }}
:root {{ --ink:#1b2620; --muted:#55615a; --accent:#2f6b4f; --line:#d9d5ca; --warn:#8a5a12; }}
* {{ box-sizing: border-box; }}
body {{ font: {BODY_PT}pt/1.38 'Inter', 'Helvetica Neue', Arial, sans-serif; color: var(--ink); margin: 0; }}
h1 {{ font: 400 22pt/1.1 Georgia, serif; margin: 0; letter-spacing: -.02em; }}
h1 em {{ color: var(--accent); }}
h2 {{ font: 700 8pt/1.3 ui-monospace, Menlo, monospace; letter-spacing: .12em; text-transform: uppercase; color: var(--accent); margin: 10pt 0 4pt; }}
h3 {{ font-size: 11.5pt; margin: 0 0 3pt; line-height: 1.25; }}
p {{ margin: 0 0 4pt; }}
.mast {{ display:flex; justify-content:space-between; align-items:flex-end; border-bottom: 2px solid var(--ink); padding-bottom: 6pt; }}
.stamp {{ font: 700 8pt ui-monospace, monospace; color: var(--warn); border: 1px solid var(--warn); padding: 2pt 5pt; }}
.card {{ display:grid; grid-template-columns: 52mm 1fr; gap: 8pt; border-top: 1px solid var(--line); padding: 7pt 0; break-inside: avoid; }}
.viz {{ margin:0; color: var(--ink); }} .viz svg {{ width: 52mm; height: auto; display:block; }}
.viz figcaption, .fn, .tag {{ font-size: 8.5pt; color: var(--muted); }}
.placeholder {{ border: 1.5px dashed var(--warn); color: var(--warn); font-size: 9pt; padding: 6pt; min-height: 30mm; }}
.quote {{ border-left: 3px solid var(--line); padding-left: 6pt; color: var(--muted); }}
.strip {{ width:100%; border-collapse: collapse; font-size: 8.5pt; }} .strip th, .strip td {{ border-bottom: 1px solid var(--line); padding: 2pt 3pt; text-align:left; vertical-align: top; }}
ol.refs {{ font-size: 8.5pt; padding-left: 14pt; }} ol.refs a {{ color: var(--ink); overflow-wrap:anywhere; }}
.page2 {{ break-before: page; }}
ul {{ margin: 0 0 4pt; padding-left: 14pt; }}
:root {{ --atom-o:#c0392b; --atom-n:#2c5fb3; }}
</style></head><body>
<section class="page1">
<div class="mast"><div><h2 style="margin:0 0 2pt">BIOPOLYMER Intelligence · Monthly</h2><h1>{_e(label(month))} <em>evidence brief</em></h1></div><span class="stamp">{_e(stamp)}</span></div>
<h2>What changed this month</h2><p>{_e(what)}</p>
{''.join(page1_cards) or '<p class="fn">No lead cards yet.</p>'}
</section>
<section class="page2">
{''.join(page2_cards)}
{('<h2>Comparison</h2>' + comp) if comp else ''}
{('<h2>Watchlist</h2><ul>' + watch + '</ul>') if watch else ''}
{('<h2>Follow-up questions</h2><ol>' + qs + '</ol>') if qs else ''}
{('<h2>Editorial notes</h2><ul class="fn">' + notes + '</ul>') if notes else ''}
<h2>References</h2><ol class="refs">{''.join(refs) or '<li>None.</li>'}</ol>
<p class="fn">{_e(site['name'])} · {_e(config()['site']['url'] + config()['site']['base'])}/newsletter/{month}/ · Content CC BY 4.0 · Not technical, regulatory or purchasing advice.</p>
</section></body></html>"""


def render_pdf(html_path: Path, pdf_path: Path, png_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 794, "height": 1123})
        page.goto(html_path.resolve().as_uri())
        page.pdf(path=str(pdf_path), format="A4", prefer_css_page_size=True, print_background=True)
        page.emulate_media(media="print")
        page.screenshot(path=str(png_path), clip={"x": 0, "y": 0, "width": 794, "height": 1123})
        b.close()


def check_numbers(issue: dict, devs: dict) -> list[str]:
    """Every number in drafted card text must exist in that card's evidence record."""
    bad = []
    for c in issue.get("cards") or []:
        record = json.dumps(devs.get(c["development"], {}), ensure_ascii=False)
        for field in ("headline", "change", "implication", "gap"):
            for n in numbers(c.get(field, "")):
                if not number_in(n, record):
                    bad.append(f"card {c['development']}.{field}: number {n} is not in the evidence record")
    return bad


def build(month: str, pdf: bool = True, log=print) -> bool:
    from pypdf import PdfReader

    issue = _yaml(DATA / "newsletter" / f"{month}.yaml", None)
    if issue is None:
        log(f"no data/newsletter/{month}.yaml")
        return False
    devs = {d["id"]: d for d in _yaml(DATA / "developments" / f"{month}.yaml", []) or []}
    lf = DATA / "leads" / f"{month}.json"
    leads = {c["id"]: c for c in json.loads(lf.read_text())["leads"]} if lf.exists() else {}
    paths = issue_paths(month)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    doc = render_html(month, issue, devs, leads)
    paths["html"].write_text(doc)
    text = re.sub(r"(?is)<style.*?</style>|<svg.*?</svg>", " ", doc)
    words = word_count(html.unescape(re.sub(r"<[^>]+>", " ", text)))
    problems = check_numbers(issue, devs)
    final = issue["layout_status"] == "final"
    if final and not 350 <= words <= 500:
        problems.append(f"word count {words} outside 350-500")
    for c in issue.get("cards") or []:
        hw = word_count(c.get("headline", ""))
        cw = sum(word_count(c.get(k, "")) for k in ("headline", "change", "implication", "gap"))
        if final and not 5 <= hw <= 9:
            problems.append(f"card {c['development']}: headline has {hw} words (5-9)")
        if final and not 45 <= cw <= 70:
            problems.append(f"card {c['development']}: {cw} words (45-70)")
    pages = None
    if pdf:
        render_pdf(paths["html"], paths["pdf"], paths["png"])
        pages = len(PdfReader(str(paths["pdf"])).pages)
        if pages > 2:
            problems.append(f"rendered PDF has {pages} pages (max 2): reduce item count, not font size")
    result = {"month": month, "built": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": issue["status"],
              "layout_status": issue["layout_status"], "pages": pages, "words": words, "body_pt": BODY_PT,
              "problems": problems, "html": f"newsletter/{paths['html'].name}",
              "pdf": f"newsletter/{paths['pdf'].name}" if pdf else None, "cover": f"newsletter/{paths['png'].name}" if pdf else None}
    paths["build"].write_text(json.dumps(result, indent=2) + "\n")
    log(json.dumps(result, indent=2))
    return not problems


def draft(month: str, log=print) -> None:
    """Draft card text with the draft model from evidence-record fields only (max 3 calls), then re-check numbers.
    Draft text is written back to the issue YAML for human editing; it never changes the issue status."""
    from pydantic import BaseModel

    from .llm import LLM, have_key

    path = DATA / "newsletter" / f"{month}.yaml"
    issue = yaml.safe_load(path.read_text())
    devs = {d["id"]: d for d in _yaml(DATA / "developments" / f"{month}.yaml", []) or []}
    ready = [c for c in issue.get("cards") or [] if devs.get(c["development"], {}).get("review", {}).get("status") in ("evidence-checked", "signed")]
    if not ready:
        log("No evidence-checked developments: nothing to draft. The issue stays a skeleton.")
        return
    if not have_key():
        log("DEEPSEEK_API_KEY not set: drafting skipped.")
        return

    class Card(BaseModel):
        headline: str
        change: str
        implication: str
        gap: str

    llm = LLM(budget=llm_config()["max_draft_calls"])
    model = draft_model()
    llm.check_models(model)
    system = ("Write one newsletter lead card in plain British English from the evidence record given. Use ONLY facts and numbers in the record. "
              "headline: 5-9 words, conclusion first. change, implication, gap: one sentence each; 45-70 words in total. "
              "Attribute supplier claims. Never infer biodegradability, compostability, bio-based content or climate benefit from each other. "
              'Return JSON {"headline": "", "change": "", "implication": "", "gap": ""}.')
    for c in ready[: llm_config()["max_draft_calls"]]:
        out = llm.json_call(model, system, json.dumps(devs[c["development"]], ensure_ascii=False, default=str), Card, max_tokens=600)
        c.update(out.model_dump())
        bad = check_numbers({"cards": [c]}, devs)
        if bad:
            log(f"discarded draft for {c['development']}: {bad}")
            for k in ("headline", "change", "implication", "gap"):
                c[k] = ""
    path.write_text(yaml.safe_dump(issue, sort_keys=False, allow_unicode=True))
    log(f"drafted {len(ready)} card(s) with {model}; calls={llm.calls}")
