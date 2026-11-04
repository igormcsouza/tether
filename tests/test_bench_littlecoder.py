"""bench/run.py runner `littlecoder`: drives the little-coder agent (#218) on the same exercises."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "bench"


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.syspath_prepend(str(BENCH))
    spec = importlib.util.spec_from_file_location("bench_run_lc", BENCH / "run.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bench_run_lc"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_build_cmd_runs_the_launcher_headless_in_print_mode(
    run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LITTLE_CODER_DIR", str(tmp_path / "lc"))
    cmd = run.build_cmd(
        "littlecoder", "ollama/qwen3.5:9b", "poly-bowling", "GOAL TEXT", "/ws", "/rd", "tether"
    )
    assert cmd[:2] == ["node", str(tmp_path / "lc" / "bin" / "little-coder.mjs")]
    for flag in ("--no-update-check", "-p", "--no-session"):
        assert flag in cmd
    assert cmd[cmd.index("--model") + 1] == "ollama/qwen3.5:9b"
    assert cmd[-1] == "GOAL TEXT", "the goal is the trailing prompt"


def test_build_cmd_default_install_dir_is_inside_bench(
    run, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LITTLE_CODER_DIR", raising=False)
    cmd = run.build_cmd("littlecoder", "ollama/qwen3.5:9b", "poly-x", "g", "/ws", "/rd", "tether")
    assert cmd[1] == str(BENCH / ".little-coder" / "bin" / "little-coder.mjs")


def test_env_points_it_at_ollama_with_a_16k_window_and_stays_inside_the_run_dir(
    run, tmp_path: Path
) -> None:
    env = run.little_coder_env(str(tmp_path), context_tokens=16384)
    models = json.loads(Path(env["LITTLE_CODER_MODELS_FILE"]).read_text())
    prov = models["providers"]["ollama"]
    assert prov["baseUrl"] == "http://localhost:11435/v1"
    assert prov["models"][0]["id"] == "qwen3.5:9b" and prov["models"][0]["contextWindow"] == 16384
    assert env["PI_CODING_AGENT_DIR"].startswith(str(tmp_path)), "no state outside the run dir"
    assert env["LITTLE_CODER_PERMISSION_MODE"] == "accept-all"
    assert env["OLLAMA_API_KEY"] and env["PI_SKIP_VERSION_CHECK"] == "1"
    assert int(env["LITTLE_CODER_MAX_TURNS"]) > 0


def test_a_littlecoder_timeout_is_not_called_infra(run) -> None:
    rec = {"runner": "littlecoder", "run_status": "timeout", "exit": -9, "steps": None}
    assert run.is_infra(rec) is False


def test_sandboxed_confines_the_agent_to_its_run_dir(
    run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    node_bin = tmp_path / "node" / "bin"
    node_bin.mkdir(parents=True)
    (node_bin / "node").write_text("")
    monkeypatch.setattr(run.shutil, "which", lambda name: str(node_bin / "node"))
    monkeypatch.setenv("LITTLE_CODER_DIR", str(tmp_path / "lc"))
    inner = ["node", "launcher.mjs", "-p", "GOAL"]
    cmd = run.sandboxed(inner, "/run/ws", "/run", "/skills/sandbox.sh")
    assert cmd[0] == "env"
    assert "GRU_SANDBOX_RW=/run" in cmd, "the agent may write only inside the run dir"
    ro = next(c for c in cmd if c.startswith("GRU_SANDBOX_RO="))
    assert str(tmp_path / "lc") in ro and str(tmp_path / "node") in ro
    i = cmd.index("/skills/sandbox.sh")
    assert cmd[i : i + 3] == ["/skills/sandbox.sh", "/run/ws", "--"]
    assert any(c == f"PATH={node_bin}:/usr/bin:/bin" for c in cmd), "node must resolve inside"
    assert cmd[-len(inner) :] == inner


def test_unknown_runner_still_fails_loudly(run) -> None:
    with pytest.raises(SystemExit):
        run.build_cmd("nope", "ollama/qwen3.5:9b", "poly-x", "g", "/ws", "/rd", "tether")


async def test_one_runs_the_launcher_in_the_workspace_and_records_the_result(
    run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import argparse
    import asyncio

    lc = tmp_path / "lc"
    (lc / "bin").mkdir(parents=True)
    (lc / "bin" / "little-coder.mjs").write_text(
        "import {writeFileSync} from 'node:fs';"
        "writeFileSync('ran.txt', process.env.LITTLE_CODER_PERMISSION_MODE);"
        "console.log('final answer');\n"
    )
    monkeypatch.setenv("LITTLE_CODER_DIR", str(lc))
    out = tmp_path / "out"
    out.mkdir()
    args = argparse.Namespace(
        out=str(out), force=False, redo_infra=False, tether_bin="tether", param=[],
        seeded=False, context_tokens=None,
    )  # fmt: skip
    sem = {"ollama": asyncio.Semaphore(1)}
    results: list = []
    await run.one(sem, ("littlecoder", "ollama/qwen3.5:9b", "code-simple", 0), args, results)
    info = results[0]
    assert info["runner"] == "littlecoder" and info["exit"] == 0 and "db_error" not in info
    assert (Path(info["dir"]) / "ws" / "ran.txt").read_text() == "accept-all"
    assert "final answer" in (Path(info["dir"]) / "result.txt").read_text()
    assert json.loads((Path(info["dir"]) / "models.json").read_text())["providers"]["ollama"]


async def test_one_wraps_the_agent_in_the_sandbox_when_one_is_configured(
    run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import argparse
    import asyncio

    box = (
        tmp_path / "sandbox.sh"
    )  # a stand-in that records how it was called, then runs the command
    box.write_text('#!/bin/sh\necho "$@" > "$GRU_SANDBOX_RW/box-args.txt"\nshift 2\nexec "$@"\n')
    box.chmod(0o755)
    lc = tmp_path / "lc"
    (lc / "bin").mkdir(parents=True)
    (lc / "bin" / "little-coder.mjs").write_text("console.log('ok');\n")
    monkeypatch.setenv("LITTLE_CODER_DIR", str(lc))
    monkeypatch.setenv("LITTLE_CODER_SANDBOX", str(box))
    out = tmp_path / "out"
    out.mkdir()
    args = argparse.Namespace(
        out=str(out), force=False, redo_infra=False, tether_bin="tether", param=[],
        seeded=False, context_tokens=None,
    )  # fmt: skip
    results: list = []
    await run.one(
        {"ollama": asyncio.Semaphore(1)},
        ("littlecoder", "ollama/qwen3.5:9b", "code-simple", 0),
        args,
        results,
    )
    rd = Path(results[0]["dir"])
    assert (rd / "box-args.txt").exists(), "the sandbox wrapper ran, with the run dir as RW"
    assert str(rd / "ws") in (rd / "box-args.txt").read_text()
