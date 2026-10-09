from engine import rank, store

CFG = store.load_config("frontal")
ACC = {"company": "Ostrom", "domain": "ostrom.example"}


def feat(size=120, buyer_name="Dana", fit="pass"):
    return {"domain": "ostrom.example", "employee_estimate": size, "buyer_title": "VP Sales", "buyer_name": buyer_name,
            "fit": {f: {"verdict": fit, "reason": "ok"} for f in ("industry", "size", "region", "must_have")}}


def sig(name, occurred, announced=True, date="2026-10-08", source="https://s"):
    return {"date": date, "domain": "ostrom.example", "company": "Ostrom", "signal": name, "evidence": f"{name} evidence",
            "occurred_on": occurred, "source": source, "announced": announced, "confidence": "high"}


def test_fit_fail_suppresses(tmp_root):
    store.append_jsonl(store.DATA / "signals.jsonl", sig("funding_round", "2026-10-01"))
    r = rank.rank_account(ACC, feat(size=5000), CFG, "2026-10-08")
    assert r["status"] == "suppress" and "size:fail" in r["why"]


def test_layoffs_hold(tmp_root):
    store.append_jsonl(store.DATA / "signals.jsonl", sig("funding_round", "2026-10-01"))
    store.append_jsonl(store.DATA / "signals.jsonl", sig("layoffs", "2026-09-20"))
    r = rank.rank_account(ACC, feat(), CFG, "2026-10-08")
    assert r["status"] == "hold" and "layoffs" in r["why"]


def test_stale_signal_holds(tmp_root):
    store.append_jsonl(store.DATA / "signals.jsonl", sig("job_posting", "2026-08-01"))
    r = rank.rank_account(ACC, feat(), CFG, "2026-10-08")
    assert r["status"] == "hold" and "window" in r["why"]


def test_act_scores_and_stack(tmp_root):
    store.append_jsonl(store.DATA / "signals.jsonl", sig("funding_round", "2026-10-06"))
    r1 = rank.rank_account(ACC, feat(), CFG, "2026-10-08")
    assert r1["status"] == "act" and r1["second"] == 0 and r1["opener_signal"] == "funding_round"
    store.append_jsonl(store.DATA / "signals.jsonl", sig("job_repost", "2026-10-07", source="https://s2"))
    r2 = rank.rank_account(ACC, feat(), CFG, "2026-10-08")
    assert r2["stacked"] and r2["score"] > r1["score"]
    assert r2["icp"] + r2["buyer_pts"] + r2["recency"] + r2["relevance"] + r2["second"] == r2["score"]


def test_unknown_fit_holds_not_suppresses(tmp_root):
    store.append_jsonl(store.DATA / "signals.jsonl", sig("new_leader", "2026-10-05"))
    r = rank.rank_account(ACC, feat(size=None, fit="unknown"), CFG, "2026-10-08")
    assert r["status"] == "hold" and "fit unknown" in r["why"]


def test_watched_signal_never_becomes_opener(tmp_root):
    store.append_jsonl(store.DATA / "signals.jsonl", sig("website_visit", "2026-10-07", announced=False))
    r = rank.rank_account(ACC, feat(), CFG, "2026-10-08")
    assert r["status"] == "act" and r["opener_fact"] == "" and "no announced fact" in r["why"]


def test_same_family_signals_do_not_stack(tmp_root):
    store.append_jsonl(store.DATA / "signals.jsonl", sig("job_posting", "2026-10-06"))
    store.append_jsonl(store.DATA / "signals.jsonl", sig("hiring_campaign", "2026-10-07", source="https://s2"))
    r = rank.rank_account(ACC, feat(), CFG, "2026-10-08")
    assert r["status"] == "act" and not r["stacked"] and r["second"] == 0
