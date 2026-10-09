"""Haiku vs Sonnet vs your labels on labeled diffs. Decides whether Read stays on Haiku.

  python evals/agreement.py evals/labeled.jsonl
Label 100 to 200 real diffs by hand first. Rows: {"rec": <diff record>, "expected": [signal names]}.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import llm, read, store  # noqa: E402


def run(path: str, models=(llm.HAIKU, llm.SONNET)):
    cfg = store.load_config("frontal")
    rows = [json.loads(l) for l in open(path) if l.strip()]
    results = {m: {"exact": 0, "tp": 0, "fp": 0, "fn": 0, "usd": 0.0} for m in models}
    for row in rows:
        exp = set(row["expected"])
        for m in models:
            got = read.read_record(row["rec"], cfg, model=m)
            names = {g["signal"] for g in got}
            r = results[m]
            r["exact"] += names == exp
            r["tp"] += len(names & exp); r["fp"] += len(names - exp); r["fn"] += len(exp - names)
            r["usd"] += sum(g["usd"] for g in got) if got else 0
    print(f"{'model':<20} {'exact':>6} {'prec':>6} {'rec':>6} {'usd':>8}")
    for m, r in results.items():
        p = r["tp"] / (r["tp"] + r["fp"]) if r["tp"] + r["fp"] else 0
        rc = r["tp"] / (r["tp"] + r["fn"]) if r["tp"] + r["fn"] else 0
        print(f"{m:<20} {r['exact']/len(rows):>6.0%} {p:>6.0%} {rc:>6.0%} {r['usd']:>8.4f}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "evals/labeled.jsonl")
