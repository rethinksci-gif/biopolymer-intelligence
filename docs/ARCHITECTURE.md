# Architecture

BIOPOLYMER Intelligence is a sister of [BIOGLUE Intelligence](https://github.com/rethinksci-gif/bioglue-intelligence) (reference commit `4d1edcb`). It reuses BIOGLUE's stack and design system and changes the domain, cadence (monthly, not quarterly) and evidence tooling.

## Reused from BIOGLUE (copied and adapted, not rewritten)

| Area | BIOGLUE source | Here |
|---|---|---|
| Static site | Astro 7 + Pagefind (`site/`) | Same versions, same `astro.config.mjs` pattern, `base: /biopolymer-intelligence` |
| Layout + tokens | `layouts/Base.astro`, `styles/global.css`, `styles/home.css` | Same CSS tokens, Inter + Georgia typography, dark mode (`prefers-color-scheme` + manual toggle with `localStorage`), header/footer, route cards, `FIG.` hero panel, numbered eyebrows, radar layout, explore band |
| Components | `Mol.astro`, `Leads.astro` | Extended: role-label chips, PubChem/source links; novelty/source/region chips and filter data attributes |
| Scanner | `scanner/{config,llm,sources,triage}.py` | Same structure: JSON mode + pydantic, per-run budget, verbatim-quote rule, 0.6 threshold, abstracts dropped after triage |
| Structures | `scanner/structures.py` (RDKit, theme-aware SVG) | Same rendering; verification extended (below) |
| Reference check | `verify-refs` (Crossref title match) | Same, extended to quotes |
| Search, RSS, open data, BibTeX | `search.astro`, `rss.xml.ts`, `data/[...file].json.ts`, `references.bib.ts` | Same approach; RSS adds newsletter issues; data export adds CSV |
| Workflows | `ci.yml`, `pages.yml`, `scan.yml` | `ci.yml`, `deploy.yml`, `monthly.yml` |
| Issue templates | `lead.yml`, `correction.yml` | Same plus `structure.yml` |

## What changed

- **Cadence and windows**: `scanner/months.py` (previous calendar month by default) replaces quarters. Leads in `data/leads/YYYY-MM.json`, runs in `data/runs/YYYY-MM.json`.
- **Discovery**: OpenAlex and Europe PMC added to Crossref and Google News; Crossref also returns `posted-content` (preprints, lead-only); Google News in de/fr/zh/ja editions; cancellation/delay queries. A code-side keyword gate (`config/site.yaml`) drops off-topic records before any LLM call.
- **Triage**: novelty type (4 ids), region, quote location; numbers in a summary must occur in the quote as whole numbers (`scanner/checks.py`); records after the cutoff are rejected; budget is spent on focus routes first; every record is hashed (DOI or URL + title) and never re-sent across months (`data/cache/triaged.json`).
- **Models**: `config/llm.yaml` with `DEEPSEEK_TRIAGE_MODEL` (flash) and an optional `DEEPSEEK_DRAFT_MODEL` (unset by default). Each run calls `GET /models` and stops if a configured model is missing; there is no fallback to retired names. Token use per model is logged.
- **Structures**: every non-polymer structure must match its PubChem CID's InChIKey (cached); repeat units (`*` SMILES) are capped and hydrolysed in RDKit and must yield exactly the listed library monomers — this catches wrong stereocentres in repeat units. Repeat units get brackets and `n`.
- **References and statements**: `verify-refs` also re-finds every `support` quote in the reference's abstract (Crossref + OpenAlex; abstracts are not stored) and every official-document quote in `data/sources.yaml` on the issuing body's page (CELLAR for EUR-Lex documents).
- **Evidence records**: `schemas/development.schema.json` implements the 12-point record; `scanner/validate.py` adds rules schemas cannot express.
- **Newsletter**: `scanner/newsletter.py` renders a two-page A4 HTML, prints it to PDF with Playwright, counts pages with pypdf, counts words and re-checks numbers against evidence records.
- **QA**: `scripts/qa.py` (links/anchors, axe-core in light and dark, 375 px overflow, PDF pages) and `html-validate` in CI; gitleaks job.
- **Monthly workflow** opens a pull request instead of pushing to `main`.

## Fragile in BIOGLUE, fixed here only

Not changed in the BIOGLUE repo (beyond a footer cross-link PR); worth porting:

1. **Accessibility**: links inside muted/footer text were distinguished by colour only (axe `link-in-text-block`), `.family` labels in `--accent-2` failed AA contrast on the light background, the home stats `div` used `aria-label` without a role, and the Pagefind input had only a placeholder/title. Fixed in `global.css`, `index.astro`, `search.astro`.
2. **Mobile overflow**: `.badge { white-space: nowrap }` let long badges push the page wider than 375 px. Added `.badge.wrap`.
3. **Duplicate ids** when the same molecule appears under two routes on the Chemistry page.
4. **Crossref `select`** must not include `language` (HTTP 400).
5. **Scan pushes straight to `main`**; here the monthly job opens a PR for a human to merge.
6. **Model name hard-coded** with no availability check; here each run checks `GET /models`.
7. Table headers lacked `scope` (html-validate `wcag/h63`).

## Data flow

```
config/*.yaml, prompts/triage.md
        │
scanner scan ──► data/leads/YYYY-MM.json, data/runs/YYYY-MM.json, data/cache/triaged.json
scanner structures ──► data/cache/pubchem.json, site/src/generated/structures/*.svg
scanner verify-refs ──► data/cache/verification.json
scanner newsletter build ──► site/public/newsletter/*.{html,pdf,png}, data/newsletter/YYYY-MM.build.json
site (Astro) reads data/ at build time ──► site/dist ──► GitHub Pages
```
