"""One markdown file a day. What fired, who to act on, what it cost."""
from . import llm, store


def build(today: str | None = None) -> str:
    today = today or store.today()
    queue = store.read_jsonl(store.DATA / "queue" / f"{today}.jsonl")
    sigs = [s for s in store.read_jsonl(store.DATA / "signals.jsonl") if s["date"] == today and s.get("signal") != "none"]
    diffs = store.read_jsonl(store.DATA / "diffs" / f"{today}.jsonl")
    acts = [q for q in queue if q["status"] == "act"]
    holds = [q for q in queue if q["status"] == "hold"]
    sup = [q for q in queue if q["status"] == "suppress"]
    L = [f"# Signal digest {today}", ""]
    L += [f"Accounts watched: {len(diffs)}. Changed: {sum(1 for d in diffs if d.get('sources'))}. "
          f"Signals today: {len(sigs)}. Act: {len(acts)}. Hold: {len(holds)}. Suppress: {len(sup)}.", ""]
    if sigs:
        L += ["## Fired today", "", "| Account | Signal | Date | Announced | Conf | Evidence |", "|---|---|---|---|---|---|"]
        for s in sigs:
            L.append(f"| {s['company']} | {s['signal']} | {s.get('occurred_on','')} | {'yes' if s.get('announced') else 'no'} | {s.get('confidence','')} | {s.get('evidence','')[:110].replace('|','/')} |")
        L.append("")
    if acts:
        L += ["## Act, warmest first", "", "| Score | Account | Buyer | Lead signal | Stack | Opener fact |", "|---|---|---|---|---|---|"]
        for q in acts:
            L.append(f"| {q['score']} | {q['company']} | {q['buyer']} | {q['lead_signal']} | {', '.join(q['stack'])} | {q.get('opener_fact','')[:100].replace('|','/')} |")
        L.append("")
    if holds:
        L += ["## Hold", ""] + [f"- {q['company']}: {q['why']}" for q in holds] + [""]
    if sup:
        L += ["## Suppressed", ""] + [f"- {q['company']}: {q['why'][:120]}" for q in sup] + [""]
    errs = [(d["domain"], d["errors"]) for d in diffs if d.get("errors")]
    if errs:
        L += ["## Source health", ""] + [f"- {d}: {e}" for d, e in errs] + [""]
    L += ["## Cost", "", f"At API list price (shadow cost on the subscription): today ${llm.spend(today):.4f}, month to date ${llm.spend(today[:7]):.4f}.", ""]
    text = "\n".join(L)
    out = store.DATA / "digests" / f"{today}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return text
