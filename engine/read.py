"""Diff in, signals out. Haiku reads only what changed."""
import json

from . import llm, signals, store

SCHEMA = {
    "type": "object",
    "properties": {
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "signal": {"type": "string", "enum": list(signals.TYPES)},
                    "evidence": {"type": "string"},
                    "occurred_on": {"type": "string"},
                    "source_url": {"type": "string"},
                    "announced": {"type": "boolean"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "capability": {"type": "string"},
                },
                "required": ["signal", "evidence", "occurred_on", "source_url", "announced", "confidence", "capability"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["signals"],
    "additionalProperties": False,
}


def system_prompt(cfg: dict) -> str:
    tpl = (store.ROOT / "prompts" / "read.md").read_text()
    rules = "\n".join(f"- {k}: {v}" for k, v in signals.EVIDENCE.items() if k in signals.ANNOUNCED)
    fs = "\n".join(f"- {s}: {', '.join(v)}" for s, v in signals.FROM_SOURCE.items())
    return tpl.format(company_name=cfg["company"], evidence_rules=rules, from_source=fs,
                      sales_keywords=", ".join(cfg.get("sales_role_keywords", [])))


def user_prompt(rec: dict) -> str:
    src = rec.get("sources", {})
    parts = [f"ACCOUNT: {rec['company']} ({rec['domain']})  DIFF DATE: {rec['date']}"]
    b = src.get("boards")
    if b:
        parts.append("JOB BOARD DIFF:")
        parts.append(json.dumps({k: b[k] for k in ("added", "removed", "reposts", "hiring_campaign", "open_sales", "open_total")}, ensure_ascii=False, indent=0))
    p = src.get("pages")
    if p:
        parts.append("WEBSITE PAGE DIFF (lines starting + are new, - are gone; first_seen pages have no prior snapshot and are NOT a change):")
        parts.append(json.dumps(p, ensure_ascii=False, indent=0))
    n = src.get("news")
    if n:
        parts.append("NEW NEWS HEADLINES (first time seen; the publish date is the only date you have):")
        parts.append(json.dumps(n, ensure_ascii=False, indent=0))
    return "\n".join(parts)


def read_record(rec: dict, cfg: dict, model: str = llm.HAIKU, client=None) -> list[dict]:
    if not rec.get("sources"):
        return []
    out, usage = llm.call(system_prompt(cfg), user_prompt(rec), SCHEMA, model=model,
                          tag=f"read:{rec['domain']}", client=client)
    rows = []
    for s in out.get("signals", []):
        name = signals.canonical(s["signal"]) or s["signal"]
        rows.append({"date": rec["date"], "domain": rec["domain"], "company": rec["company"],
                     "signal": name, "evidence": s["evidence"], "occurred_on": s["occurred_on"],
                     "source": s["source_url"], "announced": bool(s["announced"]) and signals.is_announced(name),
                     "confidence": s["confidence"], "capability": s.get("capability", ""),
                     "model": model, "usd": usage["usd"]})
    return rows


def read_day(day: str, cfg: dict, model: str = llm.HAIKU, log=print, client=None) -> list[dict]:
    recs = store.read_jsonl(store.DATA / "diffs" / f"{day}.jsonl")
    done = {(r["domain"], r["date"]) for r in store.read_jsonl(store.DATA / "signals.jsonl")}
    all_rows = []
    for rec in recs:
        if not rec.get("sources"):
            continue
        if (rec["domain"], rec["date"]) in done:
            log(f"  {rec['domain']:<18} already read")
            continue
        try:
            rows = read_record(rec, cfg, model, client)
        except Exception as e:
            log(f"  {rec['domain']:<18} READ FAILED: {e}")
            continue
        for r in rows:
            store.append_jsonl(store.DATA / "signals.jsonl", r)
            store.append_jsonl(store.DATA / "accounts.jsonl", {
                "company": r["company"], "domain": r["domain"], "signal": r["signal"],
                "occurred_on": r["occurred_on"], "source": r["source"], "announced": r["announced"]})
        if not rows:
            store.append_jsonl(store.DATA / "signals.jsonl", {"date": rec["date"], "domain": rec["domain"],
                               "company": rec["company"], "signal": "none", "evidence": "", "model": model})
        names = [r["signal"] for r in rows]
        log(f"  {rec['domain']:<18} {names or 'none'}")
        all_rows.extend(rows)
    return all_rows
