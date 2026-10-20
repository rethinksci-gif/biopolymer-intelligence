"""Discovery, bounded to one reporting month: Crossref, OpenAlex, Europe PMC and date-bounded Google News
RSS (English plus de/fr/zh/ja editions). Preprints are kept as leads only. Discovery is not evidence."""
from __future__ import annotations

import hashlib
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from email.utils import parsedate_to_datetime

from .config import config
from .http import get, get_json


def clean(text: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"^\s*(Abstract|ABSTRACT)\s*[:.]?\s*", "", html.unescape(text))
    return " ".join(text.split())


def norm_title(t: str) -> str:
    return "".join(ch for ch in t.casefold() if ch.isalnum())


def record_hash(r: dict) -> str:
    """Stable cache key: DOI (or normalised URL) + normalised title. A hashed record is never re-sent to the LLM."""
    key = (r.get("doi") or "").lower() or re.sub(r"[?#].*$", "", r.get("url", "")).lower()
    return hashlib.sha1(f"{key}|{norm_title(r['title'])}".encode()).hexdigest()[:20]


def _authors(names: list[str]) -> str:
    return ", ".join(names[:3]) + (" et al." if len(names) > 3 else "")


def _cr_date(parts):
    try:
        p = parts["date-parts"][0]
        return date(p[0], p[1] if len(p) > 1 else 1, p[2] if len(p) > 2 else 1).isoformat(), len(p) == 3
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def crossref(query: str, start: date, end: date, rows: int) -> list[dict]:
    params = {
        "query.bibliographic": query,
        "filter": f"from-pub-date:{start},until-pub-date:{end},type:journal-article,type:posted-content",
        "rows": rows,
        "select": "DOI,title,author,container-title,published-online,published-print,posted,issued,abstract,URL,publisher,type",
        "mailto": config()["scan"]["mailto"],
    }
    data = get_json("https://api.crossref.org/works?" + urllib.parse.urlencode(params))
    out = []
    for m in data["message"]["items"]:
        if not m.get("title"):
            continue
        dated = _cr_date(m.get("published-online")) or _cr_date(m.get("posted")) or _cr_date(m.get("published-print")) or _cr_date(m.get("issued"))
        if not dated:
            continue
        published, exact = dated
        # Crossref filters on any of its dates; keep only items whose first date is inside the window.
        if not (start.isoformat() <= published <= end.isoformat()):
            continue
        preprint = m.get("type") == "posted-content"
        out.append({
            "id": "doi:" + m["DOI"].lower(), "doi": m["DOI"].lower(),
            "source_type": "preprint" if preprint else "journal",
            "title": clean(m["title"][0]), "abstract": clean(m.get("abstract")),
            "venue": clean((m.get("container-title") or [""])[0]) or (m.get("publisher", "") if preprint else ""),
            "authors": _authors([a.get("family", "") for a in m.get("author") or []]),
            "published_date": published, "date_precision": "day" if exact else "month",
            "url": "https://doi.org/" + m["DOI"], "language": "en", "via": "crossref", "query": query,
        })
    return out


def _oa_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    pos = {p: w for w, ps in inv.items() for p in ps}
    return " ".join(pos[i] for i in sorted(pos))


def openalex(query: str, start: date, end: date, rows: int) -> list[dict]:
    params = {
        "search": query, "per-page": rows,
        "filter": f"from_publication_date:{start},to_publication_date:{end},type:article|preprint|review",
        "mailto": config()["scan"]["mailto"],
    }
    data = get_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
    out = []
    for w in data["results"]:
        if not w.get("title") or not w.get("publication_date"):
            continue
        doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
        src = ((w.get("primary_location") or {}).get("source") or {})
        out.append({
            "id": ("doi:" + doi) if doi else "openalex:" + w["id"].rsplit("/", 1)[-1], "doi": doi or None,
            "source_type": "preprint" if w.get("type") == "preprint" else "journal",
            "title": clean(w["title"]), "abstract": clean(_oa_abstract(w.get("abstract_inverted_index"))),
            "venue": src.get("display_name") or "", "authors": _authors([a["author"]["display_name"].split()[-1] for a in w.get("authorships", []) if a.get("author", {}).get("display_name")]),
            "published_date": w["publication_date"], "date_precision": "day",
            "url": w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url") or w["id"],
            "language": w.get("language") or "en", "via": "openalex", "query": query,
        })
    return [r for r in out if start.isoformat() <= r["published_date"] <= end.isoformat()]


def europepmc(query: str, start: date, end: date, rows: int) -> list[dict]:
    q = f'({query}) AND FIRST_PDATE:[{start} TO {end}]'
    params = {"query": q, "format": "json", "resultType": "core", "pageSize": rows}
    data = get_json("https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode(params))
    out = []
    for r in data.get("resultList", {}).get("result", []):
        when = r.get("firstPublicationDate")
        if not r.get("title") or not when or not (start.isoformat() <= when <= end.isoformat()):
            continue
        doi = (r.get("doi") or "").lower()
        preprint = r.get("source") == "PPR"
        out.append({
            "id": ("doi:" + doi) if doi else f"epmc:{r.get('source')}:{r.get('id')}", "doi": doi or None,
            "source_type": "preprint" if preprint else "journal",
            "title": clean(r["title"]), "abstract": clean(r.get("abstractText")),
            "venue": (r.get("journalInfo") or {}).get("journal", {}).get("title", "") or r.get("bookOrReportDetails", {}).get("publisher", ""),
            "authors": r.get("authorString", "")[:120], "published_date": when, "date_precision": "day",
            "url": f"https://doi.org/{doi}" if doi else f"https://europepmc.org/article/{r.get('source')}/{r.get('id')}",
            "language": (r.get("language") or "eng")[:2], "via": "europepmc", "query": query,
        })
    return out


def news(query: str, start: date, end: date, limit: int, lang: str = "en") -> list[dict]:
    loc = config()["scan"]["news_locales"][lang]
    q = f"{query} after:{start - timedelta(days=1)} before:{end + timedelta(days=1)}"
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, **loc})
    root = ET.fromstring(get(url))
    out = []
    for item in root.iter("item"):
        try:
            when = parsedate_to_datetime(item.findtext("pubDate")).date()
        except (TypeError, ValueError):
            continue
        if not start <= when <= end:
            continue
        title = clean(item.findtext("title"))
        out.append({
            "id": "news:" + hashlib.sha1(norm_title(title).encode()).hexdigest()[:16], "doi": None,
            "source_type": "news", "title": title, "abstract": clean(item.findtext("description")),
            "venue": clean(item.findtext("source")), "authors": "",
            "published_date": when.isoformat(), "date_precision": "day",
            "url": item.findtext("link") or "", "language": lang, "via": f"google-news:{lang}", "query": query,
        })
        if len(out) >= limit:
            break
    return out


def discover(routes: list[dict], start: date, end: date, log=print) -> tuple[list[dict], list[str]]:
    """Return (records, errors). Records are de-duplicated by id and by normalised title."""
    cfg = config()["scan"]
    seen: dict[str, dict] = {}
    by_title: dict[str, str] = {}
    errors: list[str] = []
    jobs = []
    for route in routes:
        s = route.get("scan", {})
        for q in s.get("crossref", []):
            jobs += [(route["id"], "crossref", lambda q=q: crossref(q, start, end, cfg["crossref_rows"]), q),
                     (route["id"], "openalex", lambda q=q: openalex(q, start, end, cfg["openalex_rows"]), q),
                     (route["id"], "europepmc", lambda q=q: europepmc(q, start, end, cfg["europepmc_rows"]), q)]
        for q in s.get("news", []):
            jobs.append((route["id"], "news:en", lambda q=q: news(q, start, end, cfg["news_items"]), q))
        for lang, qs in (s.get("news_i18n") or {}).items():
            for q in qs:
                jobs.append((route["id"], f"news:{lang}", lambda q=q, lang=lang: news(q, start, end, cfg["news_items"], lang), q))
    for route_id, kind, fn, q in jobs:
        try:
            items = fn()
        except Exception as exc:  # network failures are logged and reported, never fatal
            errors.append(f"{kind} '{q}': {exc}")
            log(f"  ! {kind} '{q}': {exc}")
            continue
        log(f"  {kind:10} {route_id:18} {len(items):3}  {q}")
        for it in items:
            key = by_title.get(norm_title(it["title"]), it["id"])
            entry = seen.get(key)
            if entry is None:
                entry = seen[key] = {**it, "seed_routes": []}
                by_title[norm_title(it["title"])] = key
            elif not entry.get("abstract") and it.get("abstract"):
                entry["abstract"] = it["abstract"]  # keep the richest abstract across sources
            if route_id not in entry["seed_routes"]:
                entry["seed_routes"].append(route_id)
    recs = sorted(seen.values(), key=lambda x: (x["published_date"], x["id"]))
    for r in recs:
        r["hash"] = record_hash(r)
    return recs, errors
