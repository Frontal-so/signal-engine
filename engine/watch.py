"""Snapshot, hash, diff. Only changed bytes go on to the model.

Job signals that are deterministic (repost, hiring campaign) are computed here from
posting history, so Haiku confirms and quotes rather than guesses.
"""
from datetime import date, timedelta
import difflib

from . import store
from .sources import fetch_board, fetch_news, fetch_page, sha

SALES_DEFAULT = ["sdr", "bdr", "account executive", "sales", "revenue", "growth", "outbound", "gtm", "revops"]


def norm_title(t: str) -> str:
    return " ".join((t or "").lower().replace("-", " ").split())


def is_sales_role(title: str, keywords) -> bool:
    t = norm_title(title)
    return any(k in t for k in keywords)


def _days_between(a: str | None, b: str | None) -> int | None:
    try:
        return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except Exception:
        return None


def diff_boards(prev: list[dict] | None, cur: list[dict], history: dict, today: str, keywords,
                repost_gap_days: int = 7, campaign_window: int = 30, campaign_min: int = 3,
                fresh_days: int = 21) -> dict:
    """Mutates history {posting_id: {title, first_seen, last_seen, posted_at}}. Returns the diff.

    A posting counts as added only when its own publish date is inside fresh_days, so the
    first day of watching does not report a two-month-old role as news (check 5 at the source).
    """
    prev_ids = {p["id"] for p in (prev or [])}
    cur_ids = {c["id"] for c in cur}
    added = [c for c in cur if c["id"] not in prev_ids]
    removed = [p for p in (prev or []) if p["id"] not in cur_ids]
    for c in cur:
        h = history.setdefault(c["id"], {"title": c["title"], "first_seen": today, "posted_at": c.get("posted_at"), "url": c.get("url")})
        h["last_seen"] = today
    reposts = []
    for a in added:
        t = norm_title(a["title"])
        for pid, h in history.items():
            if pid == a["id"] or norm_title(h["title"]) != t:
                continue
            gone = h.get("last_seen")
            gap = _days_between(gone, today)
            if h.get("first_seen") and gone and gone < today and (gap is None or gap >= repost_gap_days):
                reposts.append({"title": a["title"], "first_posted": h.get("posted_at") or h["first_seen"],
                                "gone_since": gone, "reposted": a.get("posted_at") or today, "url": a.get("url")})
                break
    cutoff = (date.fromisoformat(today) - timedelta(days=campaign_window)).isoformat()
    fresh_cutoff = (date.fromisoformat(today) - timedelta(days=fresh_days)).isoformat()
    added_all = added
    added = [a for a in added_all if (a.get("posted_at") or today) >= fresh_cutoff]
    recent_sales = [h for h in history.values()
                    if (h.get("posted_at") or h.get("first_seen", "")) >= cutoff and is_sales_role(h["title"], keywords)]
    campaign = [{"title": h["title"], "posted_at": h.get("posted_at") or h["first_seen"], "url": h.get("url")} for h in recent_sales] \
        if len(recent_sales) >= campaign_min else []
    sales_added = [a for a in added if is_sales_role(a["title"], keywords)]
    return {"added": added, "added_stale": len(added_all) - len(added), "removed": removed, "reposts": reposts,
            "hiring_campaign": campaign, "sales_added": sales_added, "open_total": len(cur),
            "open_sales": sum(1 for c in cur if is_sales_role(c["title"], keywords))}


def diff_pages(prev: dict | None, cur: dict, max_lines: int = 120) -> dict:
    out = {}
    for name, page in cur.items():
        old = (prev or {}).get(name, {})
        if page.get("status") != 200:
            continue
        if old.get("hash") == page["hash"]:
            continue
        if not old.get("text"):
            out[name] = {"url": page["url"], "first_seen": True, "lines": []}
            continue
        d = [l for l in difflib.unified_diff(old["text"].splitlines(), page["text"].splitlines(), lineterm="", n=1)
             if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
        if d:
            out[name] = {"url": page["url"], "first_seen": False, "lines": d[:max_lines]}
    return out


def diff_news(prev: list[dict] | None, cur: list[dict]) -> list[dict]:
    seen = {p.get("id") for p in (prev or [])}
    return [c for c in cur if c.get("id") and c["id"] not in seen and "error" not in c]


def snapshot_account(acc: dict, cfg: dict, today: str | None = None, fetch=None) -> dict:
    """One account, three sources. Writes snapshots only when something changed. Returns the diff record."""
    today = today or store.today()
    fetch = fetch or {"board": fetch_board, "page": fetch_page, "news": fetch_news}
    keywords = cfg.get("sales_role_keywords") or SALES_DEFAULT
    domain = acc["domain"]
    rec = {"date": today, "domain": domain, "company": acc["company"], "sources": {}, "errors": {}}

    if acc.get("ats") and acc.get("token"):
        try:
            cur = fetch["board"](acc["ats"], acc["token"])
            _, prev = store.latest_snapshot(domain, "boards")
            hist_path = store.snapshot_dir(domain, "boards") / "history.json"
            history = store.read_json(hist_path, {})
            d = diff_boards(prev, cur, history, today, keywords)
            store.write_json(hist_path, history)
            if prev is None or sha(cur) != sha(prev):
                store.write_json(store.snapshot_dir(domain, "boards") / f"{today}.json", cur)
            if d["added"] or (prev is not None and d["removed"]) or d["reposts"] or d["hiring_campaign"]:
                rec["sources"]["boards"] = d
        except Exception as e:
            rec["errors"]["boards"] = str(e)[:200]

    pages = {name: fetch["page"](url) for name, url in (acc.get("pages") or {}).items()}
    _, prev_pages = store.latest_snapshot(domain, "pages")
    pd = diff_pages(prev_pages, pages)
    if pd:
        store.write_json(store.snapshot_dir(domain, "pages") / f"{today}.json", pages)
        changed = {k: v for k, v in pd.items() if not v.get("first_seen")}
        if changed:
            rec["sources"]["pages"] = changed
    bad = {n: p.get("status") for n, p in pages.items() if p.get("status") != 200}
    if bad:
        rec["errors"]["pages"] = bad

    news = fetch["news"](acc.get("news_query") or acc["company"])
    if news and "error" in news[0]:
        rec["errors"]["news"] = news[0]["error"]
    else:
        _, prev_news = store.latest_snapshot(domain, "news")
        nd = diff_news(prev_news, news)
        if nd:
            store.write_json(store.snapshot_dir(domain, "news") / f"{today}.json", news)
            rec["sources"]["news"] = nd
    return rec


def snapshot_all(accounts, cfg, today=None, fetch=None, log=print) -> list[dict]:
    today = today or store.today()
    out = []
    path = store.DATA / "diffs" / f"{today}.jsonl"
    if path.exists():
        path.unlink()
    for acc in accounts:
        rec = snapshot_account(acc, cfg, today, fetch)
        changed = list(rec["sources"])
        log(f"  {acc['domain']:<18} changed={changed or '-'} errors={list(rec['errors']) or '-'}")
        store.append_jsonl(path, rec)
        out.append(rec)
    return out
