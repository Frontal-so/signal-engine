"""Plain files on purpose. When the engine is wrong you open the line that caused it."""
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("SIGNAL_ENGINE_ROOT", Path(__file__).resolve().parent.parent))
DATA = ROOT / "data"


def today() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_config(name: str = "frontal") -> dict:
    with open(ROOT / "config" / f"{name}.yaml") as f:
        return yaml.safe_load(f)


def load_accounts(path: Path | None = None) -> list[dict]:
    with open(path or ROOT / "accounts.yaml") as f:
        rows = yaml.safe_load(f).get("accounts", [])
    for r in rows:
        r.setdefault("company", r["domain"])
        r.setdefault("pages", {
            "home": f"https://{r['domain']}/",
            "about": f"https://{r['domain']}/about",
            "careers": f"https://{r['domain']}/careers",
            "pricing": f"https://{r['domain']}/pricing",
        })
        r.setdefault("news_query", f'"{r["company"]}"')
    return rows


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def snapshot_dir(domain: str, source: str) -> Path:
    return DATA / "snapshots" / domain / source


def latest_snapshot(domain: str, source: str) -> tuple[str | None, dict | None]:
    d = snapshot_dir(domain, source)
    if not d.exists():
        return None, None
    files = sorted(p for p in d.glob("*.json") if p.stem != "history")
    if not files:
        return None, None
    return files[-1].stem, read_json(files[-1])
