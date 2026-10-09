from engine import watch

KW = ["sdr", "account executive", "sales", "growth"]


def P(i, title, posted):
    return {"id": i, "title": title, "location": "Remote", "posted_at": posted, "url": f"https://x/{i}"}


def test_repost_detected_after_gap():
    hist = {}
    d1 = watch.diff_boards(None, [P("a", "Account Executive", "2026-09-04")], hist, "2026-09-04", KW)
    assert d1["added"] and not d1["reposts"]
    d2 = watch.diff_boards([P("a", "Account Executive", "2026-09-04")], [], hist, "2026-09-20", KW)
    assert d2["removed"]
    d3 = watch.diff_boards([], [P("b", "Account Executive", "2026-10-07")], hist, "2026-10-07", KW)
    assert len(d3["reposts"]) == 1
    assert d3["reposts"][0]["first_posted"] == "2026-09-04"


def test_syndication_same_day_is_not_repost():
    hist = {}
    watch.diff_boards(None, [P("a", "SDR", "2026-10-01")], hist, "2026-10-01", KW)
    d = watch.diff_boards([P("a", "SDR", "2026-10-01")], [P("a", "SDR", "2026-10-01"), P("b", "SDR", "2026-10-01")], hist, "2026-10-01", KW)
    assert not d["reposts"]


def test_stale_added_postings_are_filtered():
    hist = {}
    d = watch.diff_boards(None, [P("a", "SDR", "2026-07-01"), P("b", "SDR", "2026-10-05")], hist, "2026-10-08", KW)
    assert [a["id"] for a in d["added"]] == ["b"] and d["added_stale"] == 1


def test_hiring_campaign_needs_three_sales_roles():
    hist = {}
    cur = [P("1", "SDR", "2026-10-01"), P("2", "Account Executive", "2026-10-02"), P("3", "Backend Engineer", "2026-10-02")]
    d = watch.diff_boards(None, cur, hist, "2026-10-03", KW)
    assert not d["hiring_campaign"]
    cur.append(P("4", "Head of Sales", "2026-10-03"))
    d = watch.diff_boards(cur[:3], cur, hist, "2026-10-03", KW)
    assert len(d["hiring_campaign"]) == 3
    assert d["open_sales"] == 3


def test_page_diff_only_on_change():
    old = {"pricing": {"url": "u", "status": 200, "text": "Pro $49/mo\nTeam $99/mo", "hash": "h1"}}
    new_same = {"pricing": {"url": "u", "status": 200, "text": "Pro $49/mo\nTeam $99/mo", "hash": "h1"}}
    assert watch.diff_pages(old, new_same) == {}
    new = {"pricing": {"url": "u", "status": 200, "text": "Pro $59/mo\nTeam $99/mo", "hash": "h2"}}
    d = watch.diff_pages(old, new)
    assert d["pricing"]["lines"] == ["-Pro $49/mo", "+Pro $59/mo"]
    first = watch.diff_pages(None, new)
    assert first["pricing"]["first_seen"] is True


def test_news_diff_is_new_ids_only():
    prev = [{"id": "1", "title": "a"}]
    cur = [{"id": "1", "title": "a"}, {"id": "2", "title": "b"}]
    assert [n["id"] for n in watch.diff_news(prev, cur)] == ["2"]


def test_fetch_board_rejects_error_pages(monkeypatch):
    from engine import sources

    class R:
        def __init__(self, payload): self._p = payload
        def json(self): return self._p
    monkeypatch.setattr(sources, "_get", lambda url, **kw: R({"error": "not found"}))
    import pytest
    with pytest.raises(ValueError):
        sources.fetch_board("greenhouse", "nope")
    with pytest.raises(ValueError):
        sources.fetch_board("ashby", "nope")
    monkeypatch.setattr(sources, "_get", lambda url, **kw: R({"jobs": []}))
    assert sources.fetch_board("greenhouse", "empty") == []
    assert sources.probe_board("greenhouse", "empty") is True
