"""One door to the model. Structured output, cached system prompt, cost per call logged.

Two backends:
  claude  (default) Claude Code headless, `claude -p --model haiku --json-schema ...`.
          Runs on the Claude subscription. No API key. Needs `claude` logged in once.
  api     Anthropic SDK with ANTHROPIC_API_KEY in .env. Billed per token.
Pick with SIGNAL_ENGINE_BACKEND=claude|api.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

from . import store

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
# Pass full model IDs: the CLI's "haiku" alias resolved to Haiku 4.5 on 2026-10-08.
BACKEND = os.environ.get("SIGNAL_ENGINE_BACKEND", "claude")
# $/MTok. Haiku 5.5 tiers at 100K input tokens; cache read/write as published 2026-10-07.
PRICES = {
    HAIKU: {"in": 0.10, "out": 0.50, "cache_read": 0.01, "cache_write": 0.125,
            "long_in": 0.50, "long_out": 2.50, "long_cache_read": 0.05, "long_cache_write": 0.625},
    SONNET: {"in": 2.00, "out": 10.00, "cache_read": 0.10, "cache_write": 2.50},
}


def cost_usd(model: str, usage: dict) -> float:
    """What the call would cost at API list price. On the subscription it is a shadow number."""
    p = PRICES.get(model, PRICES[SONNET])
    inp = usage.get("input_tokens", 0) or 0
    cr = usage.get("cache_read_input_tokens", 0) or 0
    cw = usage.get("cache_creation_input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    long = model == HAIKU and (inp + cr + cw) > 100_000
    k = (lambda n: p.get("long_" + n, p[n])) if long else (lambda n: p[n])
    return (inp * k("in") + cr * k("cache_read") + cw * k("cache_write") + out * k("out")) / 1e6


def _client():
    import anthropic
    env = Path(store.ROOT / ".env")
    if env.exists() and not os.environ.get("ANTHROPIC_API_KEY"):
        for line in env.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY=") and len(line) > 20:
                os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip().strip('"')
    return anthropic.Anthropic()


def _call_api(system, user, schema, model, effort, max_tokens, client):
    client = client or _client()
    resp = client.messages.create(
        model=model, max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    usage = resp.usage.model_dump()
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"refusal: {getattr(resp, 'stop_details', None)}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("truncated: raise max_tokens")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text), usage, resp.model, resp.stop_reason


def _call_claude_code(system, user, schema, model, effort, timeout=600):
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("claude CLI not on PATH; install Claude Code or use SIGNAL_ENGINE_BACKEND=api")
    cmd = [exe, "-p", "--model", model, "--effort", effort,
           "--output-format", "json", "--json-schema", json.dumps(schema),
           "--system-prompt", system, "--exclude-dynamic-system-prompt-sections",
           "--tools", "", "--strict-mcp-config", "--no-session-persistence"]
    r = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "CLAUDECODE": ""})
    try:
        d = json.loads(r.stdout)
    except Exception:
        raise RuntimeError(f"claude -p returned no JSON (rc={r.returncode}): {(r.stderr or r.stdout)[:300]}")
    if d.get("is_error"):
        raise RuntimeError(f"claude -p error: {str(d.get('result'))[:300]}")
    out = d.get("structured_output")
    if out is None:
        out = json.loads(d.get("result") or "{}")
    used = list((d.get("modelUsage") or {}).keys())
    return out, d.get("usage") or {}, (used[0] if used else model), d.get("subtype")


def call(system: str, user: str, schema: dict, *, model: str = HAIKU, effort: str = "low",
         max_tokens: int = 4000, tag: str = "", client=None, backend: str | None = None) -> tuple[dict, dict]:
    """Returns (parsed_json, usage_row). Raises on refusal, truncation, or a CLI error."""
    backend = "api" if client is not None else (backend or BACKEND)
    if backend == "api":
        out, usage, served, stop = _call_api(system, user, schema, model, effort, max_tokens, client)
    else:
        out, usage, served, stop = _call_claude_code(system, user, schema, model, effort)
    row = {"ts": store.now_iso(), "backend": backend, "model": served, "tag": tag, "stop": stop,
           "usd": round(cost_usd(model, usage), 6),
           **{k: usage.get(k) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}}
    store.append_jsonl(store.DATA / "usage.jsonl", row)
    return out, row


def spend(day: str | None = None) -> float:
    rows = store.read_jsonl(store.DATA / "usage.jsonl")
    return round(sum(r["usd"] for r in rows if not day or r["ts"].startswith(day)), 4)
