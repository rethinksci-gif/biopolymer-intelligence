# BIOPOLYMER Intelligence

[![CI](https://github.com/rethinksci-gif/biopolymer-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/rethinksci-gif/biopolymer-intelligence/actions/workflows/ci.yml)
[![Site](https://img.shields.io/badge/site-live-2f6b4f)](https://rethinksci-gif.github.io/biopolymer-intelligence/)
[![Content: CC BY 4.0](https://img.shields.io/badge/content-CC%20BY%204.0-lightgrey)](LICENSE-CONTENT.md)
[![Code: MIT](https://img.shields.io/badge/code-MIT-lightgrey)](LICENSE)

An open knowledge base and **monthly** evidence tracker for **bio-based polymers**. Core focus: **PLA, PHA and PEF**, including blends and copolymers, plus new polymer chemistry with a credible bio-based connection. Sister site of [BIOGLUE Intelligence](https://rethinksci-gif.github.io/bioglue-intelligence/).

**→ https://rethinksci-gif.github.io/biopolymer-intelligence/**

Readers: Material Innovation team (possibly Raw Material team). Purpose: follow the development of bio-based polymers. The site does **not** support purchasing or qualification decisions.

| Section | What you find |
|---|---|
| [Routes](https://rethinksci-gif.github.io/biopolymer-intelligence/routes/) | 10 routes (3 focus) with chemistry, production, properties, separate end-of-life fields, challenges and a monthly track |
| [Chemistry](https://rethinksci-gif.github.io/biopolymer-intelligence/chemistry/) | 41 structures drawn from SMILES with RDKit and verified against PubChem; six explainers; sourced property table (ND where unsourced) |
| [Challenges](https://rethinksci-gif.github.io/biopolymer-intelligence/challenges/) | 12 constraints: why, how measured, what evidence the tracker looks for |
| [Tracker](https://rethinksci-gif.github.io/biopolymer-intelligence/tracker/) | Route × month; checked developments and machine-triaged leads, filterable |
| [Newsletter](https://rethinksci-gif.github.io/biopolymer-intelligence/newsletter/) | Two-page A4 monthly brief (HTML + PDF); drafts until a named reviewer signs |
| [Literature](https://rethinksci-gif.github.io/biopolymer-intelligence/references/) | Crossref-verified references by route; BibTeX/JSON/CSV |
| [Open data](https://rethinksci-gif.github.io/biopolymer-intelligence/data/) | JSON and CSV for routes, structures, leads, developments, references |

## Evidence levels

1. **Machine-triaged lead** — a Crossref / OpenAlex / Europe PMC / Google News record screened by **DeepSeek flash**. Code keeps a summary only if its quote is verbatim in the title or abstract and every number in it appears in the quote; route and novelty type must be defined ids; relevance < 0.6 is hidden; post-cutoff records are rejected.
2. **Checked development** — a 12-point evidence record; every value is a verbatim quote that contains it. Validators reject nameplate-as-output, cross-boundary LCA reductions, post-cutoff sources and unexplained repeats.
3. **Signed** — a named technical reviewer (still **OPEN**) signs the issue.

## How it works

```
data/*.yaml ─────────────────┐   schemas/*.json (CI validation)
data/leads/YYYY-MM.json ─────┼─► site/ (Astro + Pagefind) ─► GitHub Pages
data/developments/*.yaml ────┤
data/newsletter/*.yaml ──────┘──► scanner newsletter build ─► HTML + PDF (≤ 2 A4, pypdf-checked)
        ▲
        └── scanner/ (monthly GitHub Action → pull request; a human merges)
              Crossref + OpenAlex + Europe PMC + Google News (en/de/fr/zh/ja)
              ─► keyword gate ─► DeepSeek flash triage (budgeted) ─► code checks
```

- `python -m scanner scan --month YYYY-MM` — discovery + triage. Needs `DEEPSEEK_API_KEY` for triage; without it, discovery runs and leads stay "triage pending".
- `python -m scanner structures` — PubChem InChIKey verification (cached in `data/cache/pubchem.json`) + RDKit SVGs. Fails the build on any mismatch.
- `python -m scanner verify-refs` — DOIs on Crossref; every supporting quote re-found in its abstract; official-document quotes re-found on the issuing body's page.
- `python -m scanner validate` — JSON schemas + evidence rules.
- `python -m scanner newsletter build YYYY-MM` — HTML + PDF + page/word/number checks.
- `scripts/qa.py` — internal links/anchors, axe-core (light + dark), no horizontal scroll at 375 px, PDF page count.

Workflows: `ci.yml` (all checks + gitleaks), `deploy.yml` (Pages on push to `main`), `monthly.yml` (3rd of each month 05:37 UTC, previous month; opens a PR). Config: `config/llm.yaml` (models, budget — `MAX_LLM_CALLS_PER_RUN` default 60), `config/site.yaml` (sources, threshold, keyword gate).

## First run (20 Oct 2026)

September 2026: 1,328 records discovered, 296 removed by the keyword gate, 600 triaged in 60 flash calls, 200 leads shown, 433 left "triage pending" (budget). October 2026 (scanned through 20 Oct, in progress): 1,229 discovered, 337 gated, 600 triaged, 168 shown, 292 pending. Token use per run is in `data/runs/`. Trial newsletter skeleton: `/newsletter/2026-09/`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Cite with [CITATION.cff](CITATION.cff).

*Content CC BY 4.0 · Code MIT · Not technical, regulatory or purchasing advice.*
