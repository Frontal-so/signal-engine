#!/usr/bin/env python
"""signal-engine: watch accounts, read diffs with Haiku, score, rank, digest.

  python run.py import leads.csv    add companies from a CSV (company, domain); finds each job board
  python run.py snapshot            fetch boards, pages, news; write diffs (no model)
  python run.py read [--model M]    Haiku reads today's diffs into signals.jsonl
  python run.py score [--force]     Haiku answers the judgment questions per account
  python run.py rank                gate + score + status, writes queue/<date>.jsonl
  python run.py digest              markdown digest for today
  python run.py export              CSV of today's act rows for lemlist / Instantly
  python run.py daily               all of the above in order
"""
import argparse
import sys

from engine import digest, export, importer, llm, rank, read, score, store, watch


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["import", "snapshot", "read", "score", "rank", "digest", "export", "daily"])
    ap.add_argument("csv", nargs="?", help="lead list for `import`")
    ap.add_argument("--no-resolve", action="store_true", help="import: skip job-board discovery")
    ap.add_argument("--tenant", default="frontal")
    ap.add_argument("--accounts", default=None)
    ap.add_argument("--model", default=llm.HAIKU)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--day", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "import":
        if not a.csv:
            ap.error("import needs a CSV path")
        r = importer.import_csv(a.csv, store.ROOT / (a.accounts or "accounts.yaml"), resolve=not a.no_resolve)
        print(f"added {r['added']}, updated {r['updated']}, boards found {r['resolved']}, total {r['total']}")
        if r["unresolved"]:
            print("no public board found (pages and news still watched):", ", ".join(r["unresolved"]))
        return 0
    cfg = store.load_config(a.tenant)
    accounts = store.load_accounts(a.accounts)
    day = a.day or store.today()

    if a.cmd in ("snapshot", "daily"):
        print(f"snapshot {len(accounts)} accounts")
        watch.snapshot_all(accounts, cfg, day)
    if a.cmd in ("read", "daily"):
        print(f"read diffs for {day} with {a.model}")
        read.read_day(day, cfg, a.model)
    if a.cmd in ("score", "daily"):
        print(f"score accounts with {a.model}")
        score.score_all(accounts, cfg, a.model, force=a.force)
    if a.cmd in ("rank", "daily"):
        print("rank")
        rank.rank_all(accounts, cfg, day)
    if a.cmd in ("digest", "daily"):
        print(digest.build(day))
    if a.cmd in ("export", "daily"):
        print("wrote", export.export(day))
    print(f"spend today ${llm.spend(day):.4f}")


if __name__ == "__main__":
    sys.exit(main())
