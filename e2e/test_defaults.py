"""Design guarantees (the Golden Rules) checked against what really goes over the wire.

Real model in the loop (`model` parametrised over TETHER_E2E_MODELS): the assertions are about
what tether sends, so they hold for any model; task success is only a soft signal.
"""

from __future__ import annotations

from pathlib import Path

from e2e.conftest import Tether, soft
from tether.context import estimate_tokens


def _tools(req: dict) -> list[str]:
    return [t["function"]["name"] for t in req["tools"]]


def _toolbox(req: dict) -> list[str]:
    """Index lines of the [TOOLBOX] section, e.g. `- done: Complete task ...`."""
    return req["messages"][0]["content"].split("[TOOLBOX]")[1].strip().splitlines()


def _names(lines: list[str]) -> list[str]:
    return [ln.removeprefix("- ").split(":")[0].strip() for ln in lines]


def test_no_optional_tools_by_default(tmp_path: Path, chaos, model: str) -> None:
    """Rule 2: only the single `act` schema is exposed and only `done` is enabled."""
    t = Tether(tmp_path, chaos, model)
    r = t.run("Reply with the single word ok, then finish.")
    assert chaos.requests, "the model was never called"
    for req in chaos.requests:
        assert _tools(req) == ["act"]
        assert _names(_toolbox(req)) == ["done"]
    soft(
        r.get("status") == "COMPLETED",
        f"{model} did not finish the trivial task: {r.get('status')}",
    )


def test_enabled_tools_are_one_short_line_each(tmp_path: Path, chaos, model: str) -> None:
    """Rule 4: one index line per enabled tool (<= 12 tokens), schema still just `act`."""
    t = Tether(tmp_path, chaos, model)
    t.run("Reply ok then finish.", "--tools", "bash,edit,mem,web", "--max-steps", "2")
    req = chaos.requests[0]
    assert _tools(req) == ["act"]
    lines = _toolbox(req)
    assert sorted(_names(lines)) == ["bash", "done", "edit", "mem", "web"]
    assert all(estimate_tokens(ln) <= 12 for ln in lines), lines


def test_prefix_is_immutable_across_steps(tmp_path: Path, chaos, model: str) -> None:
    """Rule 1: system prompt and tools array byte-identical on every call (KV-cache reuse)."""
    t = Tether(tmp_path, chaos, model)
    t.run("Create a.txt containing hello, then finish.", "--tools", "bash,edit", "--max-steps", "6")
    assert len(chaos.requests) >= 2, "need at least two model calls to compare"
    first = chaos.requests[0]
    for req in chaos.requests[1:]:
        assert req["messages"][0] == first["messages"][0], "system prompt changed mid-session"
        assert req["tools"] == first["tools"], "tools array changed mid-session"


def test_static_framing_fits_the_token_budget(tmp_path: Path, chaos, model: str) -> None:
    """Rule: framing (system prompt + act schema + done line) < 150 tokens. Measured with the
    model's own tokenizer: the first prompt minus the goal, within a template allowance."""
    t = Tether(tmp_path, chaos, model)
    t.run("ok", "--max-steps", "1")
    used = chaos.responses[0]["prompt_eval_count"]
    soft(used < 400, f"first prompt is {used} tokens (framing should be ~150 + chat template)")
    assert used < 600, f"first prompt is {used} tokens: static framing grew"


def test_disabled_builtin_tool_error_teaches_how_to_enable(tether: Tether, chaos) -> None:
    """Rule 4.3: calling a built-in that is not enabled is a self-healing error, not a crash."""
    chaos.script("web search cats", ("done", "ok"))
    r = tether.run("use the web")
    out = tether.tool_outputs(r["id"])[0]
    assert "`web` is disabled" in out and "Enabled tools: done" in out and "--tools" in out
    assert r["rc"] == 0


def test_missing_args_return_compact_help(tether: Tether, chaos) -> None:
    """Rule 4.2: `<cmd> --help` / bad args reveal the schema JIT, in <= 60 tokens."""
    chaos.script("edit --help", "edit replace x.py", ("done", "ok"))
    r = tether.run("learn edit", "--tools", "edit")
    helps = tether.tool_outputs(r["id"])[:2]
    assert all("Usage: edit view" in h for h in helps)
    assert estimate_tokens(helps[0]) <= 60
