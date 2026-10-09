"""CSV in the shape lemlist and Instantly both import. Email is blank until an
enrichment step exists; the opener fact and the signal travel as custom columns."""
import csv

from . import store

COLS = ["email", "firstName", "lastName", "companyName", "website", "buyerTitle", "signal",
        "signalDate", "signalSource", "openerFact", "score", "stack"]


def export(today: str | None = None) -> str:
    today = today or store.today()
    rows = [q for q in store.read_jsonl(store.DATA / "queue" / f"{today}.jsonl") if q["status"] == "act"]
    out = store.DATA / "export" / f"{today}-act.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for q in rows:
            lead = next((s for s in q["signals"] if s["signal"] == q.get("opener_signal") or q["lead_signal"]), {})
            w.writerow({"email": "", "firstName": "", "lastName": "", "companyName": q["company"],
                        "website": q["domain"], "buyerTitle": q["buyer"], "signal": q["lead_signal"],
                        "signalDate": lead.get("occurred_on", ""), "signalSource": lead.get("source", ""),
                        "openerFact": q.get("opener_fact", ""), "score": q.get("score", ""), "stack": "+".join(q["stack"])})
    return str(out)
