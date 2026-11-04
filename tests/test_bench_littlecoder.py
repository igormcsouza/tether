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


def test_unknown_runner_still_fails_loudly(run) -> None:
    with pytest.raises(SystemExit):
        run.build_cmd("nope", "ollama/qwen3.5:9b", "poly-x", "g", "/ws", "/rd", "tether")
