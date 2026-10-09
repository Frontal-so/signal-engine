"""Dump a lead list in. One row per company; the importer finds the job board itself.

CSV columns: company, domain. Optional: size, country, ats, token, careers_url.
Anything else is kept on the row untouched.
"""
import csv
import re
from pathlib import Path

import yaml

from . import store
from .sources import fetch_raw, probe_board

PATTERNS = [
    (r"job-boards\.greenhouse\.io/([A-Za-z0-9_-]+)", "greenhouse"),
    (r"boards\.greenhouse\.io/([A-Za-z0-9_-]+)", "greenhouse"),
    (r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)", "greenhouse"),
    (r"greenhouse\.io/embed/job_board\?for=([A-Za-z0-9_-]+)", "greenhouse"),
    (r"jobs\.lever\.co/([A-Za-z0-9_-]+)", "lever"),
    (r"api\.lever\.co/v0/postings/([A-Za-z0-9_-]+)", "lever"),
    (r"jobs\.ashbyhq\.com/([A-Za-z0-9_-]+)", "ashby"),
    (r"api\.ashbyhq\.com/posting-api/job-board/([A-Za-z0-9_-]+)", "ashby"),
]
SKIP_TOKENS = {"embed", "v1", "v0", "posting-api", "job_board", "jobs", "boards"}


def candidate_pages(domain: str, careers_url: str | None = None) -> list[str]:
    urls = [careers_url] if careers_url else []
    urls += [f"https://{domain}/careers", f"https://{domain}/jobs", f"https://{domain}/company/careers",
             f"https://{domain}/about/careers", f"https://careers.{domain}", f"https://jobs.{domain}",
             f"https://{domain}/"]
    return [u for u in urls if u]


def tokens_in(html: str) -> list[tuple[str, str]]:
    out = []
    for pat, ats in PATTERNS:
        for m in re.finditer(pat, html):
            tok = m.group(1).lower()
            if tok not in SKIP_TOKENS and (ats, tok) not in out:
                out.append((ats, tok))
    return out


def guess_tokens(domain: str, company: str) -> list[str]:
    stem = domain.split(".")[0]
    slug = re.sub(r"[^a-z0-9]+", "", company.lower())
    hy = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
    return list(dict.fromkeys([stem, slug, hy, stem + "io", stem + "hq"]))


def resolve_ats(domain: str, company: str, careers_url: str | None = None,
                fetch=fetch_raw, probe=probe_board) -> tuple[str, str] | None:
    """Find a public ATS board for the company. Returns (ats, token) or None."""
    for url in candidate_pages(domain, careers_url):
        html = fetch(url)
        if not html:
            continue
        for ats, tok in tokens_in(html):
            if probe(ats, tok):
                return ats, tok
    for tok in guess_tokens(domain, company):
        for ats in ("greenhouse", "lever", "ashby"):
            if probe(ats, tok):
                return ats, tok
    return None


def read_csv(path: str) -> list[dict]:
    with open(path, newline="") as f:
        rows = []
        for r in csv.DictReader(f):
            r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
            if not r.get("domain"):
                continue
            r["domain"] = re.sub(r"^https?://", "", r["domain"]).split("/")[0].removeprefix("www.")
            r["company"] = r.get("company") or r["domain"].split(".")[0].title()
            if r.get("size"):
                try:
                    r["size"] = int(r["size"])
                except ValueError:
                    del r["size"]
            rows.append(r)
        return rows


def import_csv(path: str, accounts_path: Path | None = None, resolve: bool = True, log=print,
               fetch=fetch_raw, probe=probe_board) -> dict:
    accounts_path = accounts_path or store.ROOT / "accounts.yaml"
    existing = []
    if accounts_path.exists():
        with open(accounts_path) as f:
            existing = (yaml.safe_load(f) or {}).get("accounts", []) or []
    by_domain = {a["domain"]: a for a in existing}
    added, updated, resolved, unresolved = 0, 0, 0, []
    for r in read_csv(path):
        row = {k: v for k, v in r.items() if v != ""}
        careers = row.pop("careers_url", None)
        if resolve and not (row.get("ats") and row.get("token")):
            hit = resolve_ats(row["domain"], row["company"], careers, fetch, probe)
            if hit:
                row["ats"], row["token"] = hit
                resolved += 1
            else:
                unresolved.append(row["domain"])
        if careers:
            row.setdefault("pages", {})["careers"] = careers
        if row["domain"] in by_domain:
            by_domain[row["domain"]].update(row)
            updated += 1
        else:
            by_domain[row["domain"]] = row
            added += 1
        log(f"  {row['domain']:<24} {row.get('ats','-'):<11} {row.get('token','-')}")
    with open(accounts_path, "w") as f:
        f.write("# Managed by `python run.py import <leads.csv>`. Hand edits are kept on re-import.\n")
        yaml.safe_dump({"accounts": list(by_domain.values())}, f, sort_keys=False, allow_unicode=True)
    return {"added": added, "updated": updated, "resolved": resolved, "unresolved": unresolved, "total": len(by_domain)}
