"""`tether models` end to end: the proxy, a closed port and a bad providers.yaml (#310)."""

from __future__ import annotations

import json
import socket

import pytest

from e2e.conftest import Tether


@pytest.mark.ollama
def test_models_lists_pulled_models_and_declared_providers(tether: Tether, chaos) -> None:
    p = tether.cli("models", "--json", env={"OLLAMA_HOST": chaos.url})
    assert p.returncode == 0, p.stdout + p.stderr
    data = json.loads(p.stdout)
    assert data["v"] == 1 and data["ollama"]["reachable"] and data["ollama"]["models"]
    assert all(m.startswith("ollama/") for m in data["ollama"]["models"])
    prefixes = {x["prefix"] for x in data["providers"]}
    assert {"e2e", "e2eauth", "e2ecmd"} <= prefixes
    assert "sekret-value-123" not in p.stdout  # the key's name is shown, never its value
    e2eauth = next(x for x in data["providers"] if x["prefix"] == "e2eauth")
    assert e2eauth["key_env"] == "E2E_KEY" and e2eauth["key_set"] is True


def test_models_with_ollama_down_is_one_line_and_exit_zero(tether: Tether) -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = tether.cli("models", env={"OLLAMA_HOST": f"http://127.0.0.1:{port}"})
    assert p.returncode == 0, p.stdout + p.stderr
    assert "not reachable: start Ollama or set OLLAMA_HOST" in p.stdout
    assert "anthropic/<model>" in p.stdout


def test_models_with_invalid_providers_yaml_exits_one(tether: Tether, tmp_path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("x:\n  kind: nope\n")
    p = tether.cli("models", env={"TETHER_PROVIDERS": str(bad)})
    assert p.returncode == 1
    assert "providers.yaml: entry `x` has unknown kind" in p.stderr
