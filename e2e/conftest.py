"""e2e fixtures: real tether CLI, real processes, a fault-injecting proxy in front of ollama.

Local only (needs a running ollama). Enable with `TETHER_E2E=1`; point at ollama with
`TETHER_E2E_OLLAMA` (default http://localhost:11435) and pick models with `TETHER_E2E_MODELS`
(comma separated, default `qwen3.5:9b`). Scenarios marked "scripted" never use the model.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

import httpx
import pytest

from e2e.proxy import Chaos

OLLAMA = os.environ.get("TETHER_E2E_OLLAMA", "http://localhost:11435")
MODELS = [m for m in os.environ.get("TETHER_E2E_MODELS", "qwen3.5:9b").split(",") if m]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    reason = ""
    if not os.environ.get("TETHER_E2E"):
        reason = "e2e is local only: set TETHER_E2E=1"
    else:
        try:
            httpx.get(f"{OLLAMA}/api/tags", timeout=3).raise_for_status()
        except Exception as exc:
            reason = f"ollama not reachable at {OLLAMA}: {exc}"
    for item in items:
        if "e2e" in str(item.fspath) and reason:
            item.add_marker(pytest.mark.skip(reason=reason))


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "model" in metafunc.fixturenames:
        metafunc.parametrize("model", MODELS)


@pytest.fixture
def chaos() -> Any:
    c = Chaos(OLLAMA)
    yield c
    c.close()


def soft(cond: bool, msg: str) -> None:
    """A quality signal, not a gate: weak models may miss it. Shows up as a warning."""
    if not cond:
        warnings.warn(f"soft check missed: {msg}", stacklevel=2)


class Tether:
    """Drive the real CLI in a throwaway workspace whose `e2e/<model>` provider is the proxy."""

    def __init__(
        self, tmp: Path, chaos: Chaos, model: str = "scripted", timeout: int = 120
    ) -> None:
        self.ws, self.home, self.chaos, self.model = tmp / "ws", tmp / "home", chaos, model
        self.ws.mkdir()
        self.home.mkdir()
        providers = tmp / "providers.yaml"
        providers.write_text(
            f"e2e:\n  kind: ollama\n  host: {chaos.url}\n  timeout: {timeout}\n"
            f"e2eauth:\n  kind: openai\n  base_url: {chaos.url}/v1\n  api_key_env: E2E_KEY\n"
        )
        env = {
            k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and k != "OLLAMA_HOST"
        }
        self.env = env | {
            "HOME": str(self.home),
            "TETHER_PROVIDERS": str(providers),
            "E2E_KEY": "sekret-value-123",
        }

    def cli(
        self, *args: str, timeout: int = 300, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "tether.cli", *args],
            cwd=self.ws,
            env=self.env | (env or {}),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def run(
        self, goal: str, *flags: str, prefix: str = "e2e", timeout: int = 300
    ) -> dict[str, Any]:
        """`tether run --json`; returns the session dict plus `rc` and `stderr`."""
        p = self.cli(
            "run", "--json", "--model", f"{prefix}/{self.model}", *flags, goal, timeout=timeout
        )
        out = p.stdout.strip().splitlines()
        data = json.loads(out[-1]) if out and out[-1].startswith("{") else {}
        return data | {"rc": p.returncode, "stderr": p.stderr}

    def send(self, sid: str, msg: str) -> dict[str, Any]:
        p = self.cli("send", "--json", sid, msg)
        out = p.stdout.strip().splitlines()
        return (json.loads(out[-1]) if out and out[-1].startswith("{") else {}) | {
            "rc": p.returncode
        }

    def turns(self, sid: str) -> list[dict[str, Any]]:
        c = sqlite3.connect(f"file:{self.ws / '.tether' / 'tether.db'}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        return [
            dict(r) for r in c.execute("select * from turns where session_id=? order by id", (sid,))
        ]

    def events(self, sid: str) -> list[str]:
        return [t["event_type"] for t in self.turns(sid) if t["role"] == "assistant"]

    def tool_outputs(self, sid: str) -> list[str]:
        return [t["content"] for t in self.turns(sid) if t["role"] == "tool"]


@pytest.fixture
def tether(tmp_path: Path, chaos: Chaos) -> Tether:
    return Tether(tmp_path, chaos)
