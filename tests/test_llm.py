import json
from engine import llm, read, score, store


def test_cost_tiers():
    u = {"input_tokens": 10_000, "output_tokens": 500, "cache_read_input_tokens": 5_000, "cache_creation_input_tokens": 0}
    assert round(llm.cost_usd(llm.HAIKU, u), 6) == round((10_000 * 0.10 + 5_000 * 0.01 + 500 * 0.50) / 1e6, 6)
    big = {"input_tokens": 150_000, "output_tokens": 100}
    assert llm.cost_usd(llm.HAIKU, big) > llm.cost_usd(llm.HAIKU, {"input_tokens": 99_000, "output_tokens": 100}) * 1.5


def test_schemas_are_strict_json_schema():
    for s in (read.SCHEMA, score.schema(store.load_config("frontal"))):
        assert s["additionalProperties"] is False
        assert set(s["required"]) == set(s["properties"])
        json.dumps(s)


class FakeMessages:
    def __init__(self, payload):
        self.payload = payload
    def create(self, **kw):
        assert "output_config" in kw and kw["system"][0]["cache_control"]["type"] == "ephemeral"
        class R: pass
        r = R(); r.stop_reason = "end_turn"; r.model = "claude-haiku-5-5"
        class B: type = "text"
        b = B(); b.text = json.dumps(self.payload); r.content = [b]
        class U:
            def model_dump(self_inner): return {"input_tokens": 1200, "output_tokens": 80, "cache_read_input_tokens": 900, "cache_creation_input_tokens": 0}
        r.usage = U()
        return r


class FakeClient:
    def __init__(self, payload): self.messages = FakeMessages(payload)


def test_read_record_maps_rows(tmp_root):
    cfg = store.load_config("frontal")
    rec = {"date": "2026-10-08", "domain": "ostrom.example", "company": "Ostrom",
           "sources": {"boards": {"added": [], "removed": [], "reposts": [{"title": "AE", "first_posted": "2026-09-04", "gone_since": "2026-09-20", "reposted": "2026-10-07", "url": "https://x/b"}], "hiring_campaign": [], "open_sales": 1, "open_total": 3}}}
    fake = FakeClient({"signals": [{"signal": "job_repost", "evidence": "AE posted 2026-09-04, gone 2026-09-20, reposted 2026-10-07", "occurred_on": "2026-10-07", "source_url": "https://x/b", "announced": True, "confidence": "high", "capability": "closing"}]})
    rows = read.read_record(rec, cfg, client=fake)
    assert rows[0]["signal"] == "job_repost" and rows[0]["announced"] is True and rows[0]["usd"] > 0
    assert store.read_jsonl(store.DATA / "usage.jsonl")[0]["tag"] == "read:ostrom.example"


def test_claude_code_backend_parses_cli_json(tmp_root, monkeypatch):
    import subprocess
    from types import SimpleNamespace
    payload = {"type": "result", "subtype": "success", "is_error": False, "result": "{\"ok\": true}",
               "structured_output": {"ok": True}, "modelUsage": {"claude-haiku-5-5": {}},
               "usage": {"input_tokens": 500, "output_tokens": 20, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
    seen = {}
    def fake_run(cmd, **kw):
        seen["cmd"] = cmd; seen["stdin"] = kw.get("input")
        return SimpleNamespace(stdout=json.dumps(payload), stderr="", returncode=0)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(llm.shutil, "which", lambda _: "/usr/local/bin/claude")
    out, row = llm.call("SYS", "USER", {"type": "object"}, tag="t", backend="claude")
    assert out == {"ok": True} and row["model"] == "claude-haiku-5-5" and row["backend"] == "claude"
    assert "--json-schema" in seen["cmd"] and "claude-haiku-5-5" in seen["cmd"] and "--exclude-dynamic-system-prompt-sections" in seen["cmd"] and seen["stdin"] == "USER"
    assert seen["cmd"][seen["cmd"].index("--tools") + 1] == ""
