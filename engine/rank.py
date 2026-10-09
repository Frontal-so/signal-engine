"""Alex's checks, as code. Fit, person, signal, source, age, score, stack, status.

Reach (check 7) has no enrichment behind it in this build; it is reported as
"unverified" and gated only when require_reach is true.
"""
from datetime import date

from . import signals, store


def _age(occurred_on: str, today: str) -> int | None:
    try:
        return (date.fromisoformat(today) - date.fromisoformat(occurred_on[:10])).days
    except Exception:
        return None


def fit_verdict(feat: dict | None, acc: dict, cfg: dict) -> tuple[str, list[str]]:
    """pass / fail / unknown over the four fields. Registry overrides win."""
    if not feat:
        return "unknown", ["not scored yet"]
    reasons, verdicts = [], {}
    for field, v in feat["fit"].items():
        verdicts[field] = v["verdict"]
        reasons.append(f"{field}:{v['verdict']} ({v['reason'][:80]})")
    size = acc.get("size") or feat.get("employee_estimate")
    lo, hi = cfg["icp"]["size"]["min"], cfg["icp"]["size"]["max"]
    if size is not None:
        verdicts["size"] = "pass" if lo <= int(size) <= hi else "fail"
        reasons = [r for r in reasons if not r.startswith("size:")] + [f"size:{verdicts['size']} ({size} vs {lo}-{hi})"]
    if "fail" in verdicts.values():
        return "fail", reasons
    if "unknown" in verdicts.values():
        return "unknown", reasons
    return "pass", reasons


def live_signals(domain: str, today: str, cfg: dict) -> list[dict]:
    win = cfg["signal_windows_days"]
    rows = [r for r in store.read_jsonl(store.DATA / "signals.jsonl") if r["domain"] == domain and r.get("signal") not in (None, "none")]
    out = []
    for r in rows:
        age = _age(r.get("occurred_on", ""), today)
        if age is None:
            age = _age(r["date"], today)
        limit = win.get(r["signal"], win["default"])
        r = dict(r, age_days=age, window=limit, fresh=(age is not None and 0 <= age <= limit))
        out.append(r)
    # keep newest row per (signal, source) so a reread never double counts
    seen, dedup = set(), []
    for r in sorted(out, key=lambda x: x["date"], reverse=True):
        k = (r["signal"], r.get("source") or r.get("evidence", "")[:60])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(r)
    return dedup


def buyer_for(feat: dict | None, sig: dict | None, cfg: dict) -> str:
    if feat and feat.get("buyer_title"):
        return feat["buyer_title"] + (f" ({feat['buyer_name']})" if feat.get("buyer_name") else "")
    if sig:
        t = cfg["buyer_titles"]["by_signal"].get(sig["signal"])
        if t:
            return t[0]
    return cfg["buyer_titles"]["default"][0]


def rank_account(acc: dict, feat: dict | None, cfg: dict, today: str) -> dict:
    w = cfg["scoring"]
    fit, fit_reasons = fit_verdict(feat, acc, cfg)
    sigs = live_signals(acc["domain"], today, cfg)
    fresh = [s for s in sigs if s["fresh"] and s["signal"] not in signals.STATIC]
    holds = [s for s in fresh if s["signal"] in signals.HOLD]
    acts = [s for s in fresh if s["signal"] not in signals.HOLD]
    announced = [s for s in acts if s.get("announced")]
    lead = max(acts, key=lambda s: (cfg["signal_priors"].get(s["signal"], 0), -(s["age_days"] or 0)), default=None)
    distinct = {s["signal"] for s in acts}
    families = {signals.FAMILY.get(s["signal"], s["signal"]) for s in acts}
    stacked = len(families) >= cfg["stack_min"]
    row = {"date": today, "company": acc["company"], "domain": acc["domain"], "fit": fit,
           "signals": [{k: s.get(k) for k in ("signal", "occurred_on", "age_days", "announced", "confidence", "source")} for s in fresh],
           "lead_signal": lead["signal"] if lead else None, "stack": sorted(distinct), "stacked": stacked,
           "buyer": buyer_for(feat, lead, cfg), "reach": "unverified", "owner": "sdr"}
    # Check 8: pass or fail on fit, intent, recency, reach. One fail drops the account.
    if fit == "fail":
        row.update(status="suppress", why="fit: " + "; ".join(r for r in fit_reasons if ":fail" in r))
        return row
    if holds:
        row.update(status="hold", why=f"layoffs within {cfg['signal_windows_days']['layoffs']}d: {holds[0]['evidence'][:100]}")
        return row
    if not acts:
        row.update(status="hold", why="no fresh signal" if not sigs else "signals past their window")
        return row
    if fit == "unknown":
        row.update(status="hold", why="fit unknown: " + "; ".join(r for r in fit_reasons if ":unknown" in r))
        return row
    if cfg.get("require_reach") and row["reach"] != "verified":
        row.update(status="hold", why="reach unverified")
        return row
    # Components. ICP 40 when fit passes. Buyer 15 when a named person exists, 8 for a title only.
    icp = w["icp"]
    buyer = w["buyer"] if feat and feat.get("buyer_name") else int(w["buyer"] * 0.55)
    best_age = min(s["age_days"] for s in acts if s["age_days"] is not None) if any(s["age_days"] is not None for s in acts) else lead["window"]
    recency = round(w["recency"] * max(0.0, 1 - best_age / lead["window"]))
    relevance = min(w["relevance"], cfg["signal_priors"].get(lead["signal"], 0))
    second = w["second"] if stacked else 0
    score = icp + buyer + recency + relevance + second
    opener = next((s for s in announced), None)
    row.update(status="act", icp=icp, buyer_pts=buyer, recency=recency, relevance=relevance, second=second, score=score,
               opener_fact=(opener["evidence"] if opener else ""), opener_signal=(opener["signal"] if opener else None),
               why=f"{lead['signal']} {best_age}d old" + (", stacked" if stacked else "") + (", no announced fact for the opener" if not opener else ""))
    return row


def rank_all(accounts, cfg, today=None, log=print) -> list[dict]:
    from .score import latest_features
    today = today or store.today()
    feats = latest_features()
    rows = [rank_account(a, feats.get(a["domain"]), cfg, today) for a in accounts]
    order = {"act": 0, "hold": 1, "suppress": 2}
    rows.sort(key=lambda r: (order[r["status"]], -r.get("score", 0)))
    path = store.DATA / "queue" / f"{today}.jsonl"
    if path.exists():
        path.unlink()
    for r in rows:
        store.append_jsonl(path, r)
        log(f"  {r['status']:<8} {r.get('score', ''):>3} {r['domain']:<18} {r['why'][:90]}")
    return rows
