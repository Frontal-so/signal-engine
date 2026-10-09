"""Judgment scoring. Ten questions per account from its own pages, once, then on change."""
import json
from datetime import date, timedelta

from . import llm, store

FIT_FIELDS = ("industry", "size", "region", "must_have")


def schema(cfg: dict) -> dict:
    q = cfg["judgment_questions"]
    props = {
        "sells_to": {"type": "string", "enum": ["b2b", "b2c", "both", "unknown"]},
        "industry": {"type": "string"},
        "has_sales_team": {"type": "boolean"},
        "has_sales_team_evidence": {"type": "string"},
        "employee_estimate": {"type": ["integer", "null"]},
        "hq_region": {"type": ["string", "null"]},
        "open_sales_roles": {"type": "integer"},
        "outbound_motion": {"type": "boolean"},
        "outbound_motion_evidence": {"type": "string"},
        "buyer_title": {"type": "string", "maxLength": 60},
        "buyer_note": {"type": "string"},
        "buyer_name": {"type": ["string", "null"]},
        "pain_hint": {"type": "string"},
        "fit": {"type": "object",
                "properties": {f: {"type": "object", "properties": {
                    "verdict": {"type": "string", "enum": ["pass", "fail", "unknown"]},
                    "reason": {"type": "string"}}, "required": ["verdict", "reason"], "additionalProperties": False}
                    for f in FIT_FIELDS},
                "required": list(FIT_FIELDS), "additionalProperties": False},
    }
    keys = [k for k in props if k in q or k.endswith("_evidence") or k in ("fit", "buyer_note")]
    return {"type": "object", "properties": {k: props[k] for k in keys}, "required": keys, "additionalProperties": False}


def system_prompt(cfg: dict) -> str:
    tpl = (store.ROOT / "prompts" / "score.md").read_text()
    icp = cfg["icp"]
    return tpl.format(company_name=cfg["company"], icp_industry=icp["industry"], icp_size_min=icp["size"]["min"],
                      icp_size_max=icp["size"]["max"], icp_region=", ".join(icp["region"]), icp_must_have=icp["must_have"],
                      questions="\n".join(f"- {k}: {v}" for k, v in cfg["judgment_questions"].items()))


def user_prompt(acc: dict, pages: dict, postings: list[dict], per_page: int = 6000) -> str:
    parts = [f"ACCOUNT: {acc['company']} ({acc['domain']})"]
    over = {k: acc[k] for k in ("size", "country", "industry") if acc.get(k)}
    if over:
        parts.append(f"REGISTRY OVERRIDES (outrank your estimate): {json.dumps(over)}")
    for name, p in (pages or {}).items():
        if p.get("status") == 200 and p.get("text"):
            parts.append(f"--- PAGE {name} ({p['url']}) ---\n{p['text'][:per_page]}")
    if postings:
        titles = [f"{j['title']} | {j.get('location') or ''} | {j.get('posted_at') or ''}" for j in postings[:150]]
        parts.append("--- OPEN ROLES ---\n" + "\n".join(titles))
    return "\n".join(parts)


def score_account(acc: dict, cfg: dict, model: str = llm.HAIKU, client=None) -> dict:
    _, pages = store.latest_snapshot(acc["domain"], "pages")
    _, postings = store.latest_snapshot(acc["domain"], "boards")
    out, usage = llm.call(system_prompt(cfg), user_prompt(acc, pages or {}, postings or []), schema(cfg),
                          model=model, max_tokens=3000, tag=f"score:{acc['domain']}", client=client)
    out.update({"domain": acc["domain"], "company": acc["company"], "scored_on": store.today(), "model": model, "usd": usage["usd"]})
    return out


def latest_features() -> dict:
    feats = {}
    for r in store.read_jsonl(store.DATA / "features.jsonl"):
        feats[r["domain"]] = r
    return feats


def score_all(accounts, cfg, model=llm.HAIKU, force=False, max_age_days=30, log=print, client=None):
    feats = latest_features()
    cutoff = (date.today() - timedelta(days=max_age_days)).isoformat()
    for acc in accounts:
        f = feats.get(acc["domain"])
        if f and not force and f.get("scored_on", "") >= cutoff:
            log(f"  {acc['domain']:<18} fresh ({f['scored_on']})")
            continue
        try:
            row = score_account(acc, cfg, model, client)
        except Exception as e:
            log(f"  {acc['domain']:<18} SCORE FAILED: {e}")
            continue
        store.append_jsonl(store.DATA / "features.jsonl", row)
        fit = {k: v["verdict"] for k, v in row["fit"].items()}
        log(f"  {acc['domain']:<18} fit={fit} buyer={row.get('buyer_title')!r} size~{row.get('employee_estimate')}")
