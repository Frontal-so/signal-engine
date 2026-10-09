"""Fetchers. No key, no browser. Each returns a normalised, hashable record."""
import hashlib
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser

import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
TIMEOUT = 20


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "tr", "br", "section", "article"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    p = _Text()
    p.feed(raw)
    text = html.unescape("".join(p.parts))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def sha(obj) -> str:
    s = obj if isinstance(obj, str) else repr(obj)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _get(url, **kw):
    return requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, **kw)


def _date(s) -> str | None:
    if not s:
        return None
    try:
        if isinstance(s, (int, float)):
            return datetime.fromtimestamp(s / 1000 if s > 1e11 else s, tz=timezone.utc).date().isoformat()
        return str(s)[:10]
    except Exception:
        return None


def fetch_board(ats: str, token: str) -> list[dict]:
    """Postings as {id, title, location, posted_at, url}, sorted by id."""
    if ats == "greenhouse":
        d = _get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs").json()
        if not isinstance(d, dict) or "jobs" not in d:
            raise ValueError(f"greenhouse board {token!r} not found")
        rows = [{"id": str(j["id"]), "title": j["title"], "location": (j.get("location") or {}).get("name"),
                 "posted_at": _date(j.get("first_published") or j.get("updated_at")), "url": j.get("absolute_url")}
                for j in d.get("jobs", [])]
    elif ats == "lever":
        d = _get(f"https://api.lever.co/v0/postings/{token}?mode=json").json()
        if not isinstance(d, list):
            raise ValueError(f"lever board {token!r} not found")
        rows = [{"id": j["id"], "title": j["text"], "location": (j.get("categories") or {}).get("location"),
                 "posted_at": _date(j.get("createdAt")), "url": j.get("hostedUrl")} for j in d]
    elif ats == "ashby":
        d = _get(f"https://api.ashbyhq.com/posting-api/job-board/{token}").json()
        if not isinstance(d, dict) or "jobs" not in d:
            raise ValueError(f"ashby board {token!r} not found")
        rows = [{"id": j["id"], "title": j["title"], "location": j.get("location"),
                 "posted_at": _date(j.get("publishedAt")), "url": j.get("jobUrl")} for j in d.get("jobs", [])]
    else:
        raise ValueError(f"unknown ats {ats}")
    return sorted(rows, key=lambda r: r["id"])


def fetch_page(url: str, max_chars: int = 40000) -> dict:
    """{url, status, text, hash}. A non-200 is recorded, never raised."""
    try:
        r = _get(url, allow_redirects=True)
        text = html_to_text(r.text)[:max_chars] if r.status_code == 200 else ""
        return {"url": url, "status": r.status_code, "final_url": r.url, "text": text, "hash": sha(text)}
    except Exception as e:
        return {"url": url, "status": 0, "final_url": url, "text": "", "hash": sha(""), "error": str(e)[:200]}


def fetch_news(query: str, days: int = 7, max_items: int = 30) -> list[dict]:
    """Google News RSS search. Headline, source, date, link. No key."""
    q = requests.utils.quote(f"{query} when:{days}d")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        r = _get(url)
        root = ET.fromstring(r.content)
    except Exception as e:
        return [{"error": str(e)[:200]}]
    items = []
    for it in list(root.iter("item"))[:max_items]:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate") or ""
        try:
            pub_iso = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z").date().isoformat()
        except Exception:
            pub_iso = pub[:16]
        src = it.find("source")
        items.append({"id": sha(link or title), "title": title, "link": link, "published": pub_iso,
                      "source": (src.text if src is not None else "")})
    return items


def fetch_raw(url: str, max_chars: int = 400000) -> str:
    """Raw HTML, for link discovery. Empty string on any failure."""
    try:
        r = _get(url, allow_redirects=True)
        return r.text[:max_chars] if r.status_code == 200 else ""
    except Exception:
        return ""


def probe_board(ats: str, token: str) -> bool:
    try:
        fetch_board(ats, token)
        return True
    except Exception:
        return False
