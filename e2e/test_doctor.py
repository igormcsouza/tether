"""`tether doctor`: setup checks against the proxy, a closed port, and a missing model."""

from __future__ import annotations

import socket

from e2e.conftest import Tether


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _check(out: str, name: str) -> list[str]:
    """The `ok`/`FAIL` line for one check, split into words."""
    for line in out.splitlines():
        words = line.split()
        if len(words) >= 2 and words[1] == name:
            return words
    return []


def test_doctor_passes_against_the_proxy(tether: Tether, chaos, model: str) -> None:
    p = tether.cli("doctor", "--model", f"ollama/{model}", env={"OLLAMA_HOST": chaos.url})
    assert p.returncode == 0, p.stdout + p.stderr
    assert _check(p.stdout, "ollama")[:1] == ["ok"], p.stdout
    assert _check(p.stdout, "model")[:1] == ["ok"], p.stdout


def test_doctor_fails_on_a_closed_port_and_names_ollama_host(tether: Tether, chaos) -> None:
    host = f"http://127.0.0.1:{_closed_port()}"
    p = tether.cli("doctor", "--model", "ollama/qwen3.5:9b", env={"OLLAMA_HOST": host})
    assert p.returncode == 1, p.stdout + p.stderr
    words = _check(p.stdout, "ollama")
    assert words[:1] == ["FAIL"] and "OLLAMA_HOST" in " ".join(words), p.stdout


def test_doctor_tells_you_to_pull_a_missing_model(tether: Tether, chaos) -> None:
    p = tether.cli(
        "doctor",
        "--model",
        "ollama/no-such-model:1b",
        env={"OLLAMA_HOST": chaos.url},
    )
    assert p.returncode == 1, p.stdout + p.stderr
    assert _check(p.stdout, "ollama")[:1] == ["ok"], p.stdout
    assert _check(p.stdout, "model")[:1] == ["FAIL"], p.stdout
    assert "ollama pull no-such-model:1b" in p.stdout, p.stdout
