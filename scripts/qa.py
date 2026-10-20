"""Quality gates on the built site (site/dist): internal links and anchors, axe-core accessibility
(no serious/critical violations, light and dark), no horizontal scroll at 375 px, dark mode applied,
and newsletter PDFs at most 2 A4 pages. Exit code 1 on any failure.

Usage: python scripts/qa.py [--pages N]   (needs `npm ci` in site/ for axe-core, and Playwright Chromium)"""
from __future__ import annotations

import argparse
import functools
import http.server
import re
import sys
import threading
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "site" / "dist"
BASE = "/biopolymer-intelligence"
AXE = ROOT / "site" / "node_modules" / "axe-core" / "axe.min.js"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        for k in ("href", "src"):
            if a.get(k):
                self.links.append(a[k])


def page_files() -> list[Path]:
    return sorted(DIST.rglob("*.html"))


def target(path: str) -> Path | None:
    p = path[len(BASE):].lstrip("/")
    f = DIST / p
    if f.is_dir() or p == "" or p.endswith("/"):
        f = f / "index.html"
    return f if f.exists() else None


def check_links() -> list[str]:
    errors, parsed = [], {}
    for f in page_files():
        lp = Links()
        lp.feed(f.read_text(errors="ignore"))
        parsed[f] = lp
    for f, lp in parsed.items():
        if "newsletter/BIOPOLYMER" in str(f):
            continue  # print version: external links only
        for link in lp.links:
            if link.startswith(("http", "mailto:", "data:", "#")) and not link.startswith("#"):
                continue
            if link.startswith("#"):
                if link[1:] and link[1:] not in lp.ids:
                    errors.append(f"{f.relative_to(DIST)}: missing anchor {link}")
                continue
            if not link.startswith(BASE):
                errors.append(f"{f.relative_to(DIST)}: link outside base path {link}")
                continue
            path, _, frag = link.partition("#")
            t = target(path)
            if t is None:
                errors.append(f"{f.relative_to(DIST)}: broken link {link}")
            elif frag and t.suffix == ".html":
                ids = parsed.get(t).ids if t in parsed else set()
                if frag not in ids:
                    errors.append(f"{f.relative_to(DIST)}: missing anchor {link}")
    return errors


def serve() -> tuple[str, http.server.ThreadingHTTPServer]:
    root = ROOT / "site" / ".qa-root"
    root.mkdir(exist_ok=True)
    link = root / BASE.strip("/")
    if not link.exists():
        link.symlink_to(DIST, target_is_directory=True)
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):
            pass

    handler = functools.partial(Quiet, directory=str(root))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv


def browser_checks(limit: int | None) -> tuple[list[str], dict]:
    from playwright.sync_api import sync_playwright

    errors, stats = [], {"pages": 0, "axe_violations": 0, "axe_passes": 0}
    origin, srv = serve()
    pages = [f for f in page_files() if "newsletter/BIOPOLYMER" not in str(f)]
    if limit:
        pages = pages[:limit]
    axe = AXE.read_text()
    with sync_playwright() as p:
        b = p.chromium.launch()
        for scheme in ("light", "dark"):
            ctx = b.new_context(viewport={"width": 375, "height": 800}, color_scheme=scheme)
            page = ctx.new_page()
            for f in pages:
                rel = f.relative_to(DIST).as_posix().removesuffix("index.html")
                page.goto(f"{origin}{BASE}/{rel}", wait_until="load")
                over = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
                if over > 1:
                    errors.append(f"[{scheme}] /{rel}: horizontal scroll of {over}px at 375px")
                bg = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
                lum = sum(int(x) for x in re.findall(r"\d+", bg)[:3]) / 765
                if (scheme == "dark") != (lum < 0.3):
                    errors.append(f"[{scheme}] /{rel}: body background {bg} does not match the colour scheme")
                page.add_script_tag(content=axe)
                res = page.evaluate("async () => await axe.run(document, {resultTypes: ['violations']})")
                bad = [v for v in res["violations"] if v["impact"] in ("serious", "critical")]
                stats["axe_violations"] += len(bad)
                stats["axe_passes"] += len(res.get("passes", []))
                for v in bad:
                    targets = ", ".join(str(n["target"]) for n in v["nodes"][:3])
                    errors.append(f"[{scheme}] /{rel}: axe {v['impact']} {v['id']}: {v['help']} ({targets})")
                stats["pages"] += 1
            ctx.close()
        b.close()
    srv.shutdown()
    return errors, stats


def check_pdfs() -> list[str]:
    from pypdf import PdfReader

    errs = []
    for pdf in (DIST / "newsletter").glob("*.pdf"):
        n = len(PdfReader(str(pdf)).pages)
        if n > 2:
            errs.append(f"{pdf.name}: {n} pages (max 2)")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=None)
    args = ap.parse_args()
    errors = check_links()
    print(f"links: {len(errors)} problem(s)")
    pdf_errors = check_pdfs()
    print(f"newsletter PDFs: {len(pdf_errors)} problem(s)")
    b_errors, stats = browser_checks(args.pages)
    print(f"browser: {stats['pages']} page loads (light+dark at 375px), {stats['axe_violations']} serious/critical axe violations")
    errors += pdf_errors + b_errors
    for e in errors:
        print("  ✗", e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
