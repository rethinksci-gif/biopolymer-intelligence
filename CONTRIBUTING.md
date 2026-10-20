# Contributing

Thanks for helping keep this knowledge base accurate.

## Quick ways to help
- **Submit a lead**: [lead issue](../../issues/new?template=lead.yml) with the primary source.
- **Report a correction**: [correction issue](../../issues/new?template=correction.yml) with the quoted passage.
- **Suggest a structure**: [structure issue](../../issues/new?template=structure.yml) with SMILES and a citable source.

## Editing content
All site content is plain YAML/JSON under `data/`, validated against `schemas/`:

| File | What it holds |
|---|---|
| `routes.yaml` | Polymer routes: scope, background, end-of-life profile (separate fields), scan queries, quoted support |
| `chemistry.yaml` | Chemistry explainers (every paragraph cites references or official sources) and the end-of-life matrix |
| `structures.yaml` | Structures: SMILES + PubChem CID + InChIKey, or repeat units verified by hydrolysis |
| `properties.yaml` | Property table: a value only with a verbatim quote and DOI, else `ND` |
| `references.yaml` | Literature; every entry needs a DOI that resolves on Crossref |
| `sources.yaml` | Official documents without DOI (EU, Naturvårdsverket) with verbatim quotes and retrieval dates |
| `challenges.yaml`, `glossary.yaml`, `editorial.yaml` | Challenges, terms/standards, editorial scope and OPEN items |
| `leads/YYYY-MM.json` | Machine-triaged leads written by the scanner - do not hand-edit |
| `developments/YYYY-MM.yaml` | Checked developments (12-point evidence records) |
| `newsletter/YYYY-MM.yaml` | Monthly issue: status `draft` → `evidence-checked` → `signed` (reviewer + date) |
| `runs/YYYY-MM.json` | Run log: calls, tokens, cost estimate, errors |

## Evidence rules
1. Every value is a verbatim quote from a cited source; numbers must appear in the quote as whole numbers.
2. Supplier claims, nameplate capacity and laboratory results stay labelled as what they are. Nameplate is never output.
3. Never infer bio-based origin, measured bio-based carbon, mass-balance attribution, biodegradability, compostability, recyclability or climate footprint from each other.
4. No invented structures: natural polymers are shown by a representative unit; every drawing is verified.
5. Missing data is `ND` / "Not disclosed", never an estimate.

## Local setup
```bash
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev,structures,newsletter]'
.venv/bin/pytest -q && .venv/bin/python -m scanner validate
.venv/bin/python -m scanner structures          # verify against PubChem + render SVGs
.venv/bin/python -m scanner verify-refs         # Crossref + quotes (network)
.venv/bin/python -m playwright install chromium
.venv/bin/python -m scanner newsletter build 2026-09
cd site && npm ci && npm run build && cd .. && .venv/bin/python scripts/qa.py
```
A scan needs `DEEPSEEK_API_KEY` in the environment for triage (discovery runs without it):
`python -m scanner scan --month 2026-09 --max-calls 20`.
