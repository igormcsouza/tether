"""`tether doctor`: check the local setup and say what to fix."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import httpx

from tether.providers.declarative import load_declared
from tether.store import SQLiteStore


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _ollama_checks(model: str, host: str) -> list[Check]:
    name = model.removeprefix("ollama/")
    # Normalize model name: Ollama returns models with tags (e.g., qwen3.5:latest)
    # If the model name has no ':', add ':latest' for comparison
    if ":" not in name:
        name = name + ":latest"
    try:
        resp = httpx.get(f"{host}/api/tags", timeout=3)
        resp.raise_for_status()
        names = [m.get("name") for m in resp.json().get("models", [])]
    except Exception as exc:
        return [
            Check(
                "ollama",
                False,
                f"cannot reach Ollama at {host} ({exc}); start Ollama or set OLLAMA_HOST",
            ),
            Check("model", False, "cannot check: Ollama is not reachable"),
        ]
    checks = [Check("ollama", True, f"reachable at {host}")]
    if name in names:
        checks.append(Check("model", True, f"{name} is pulled"))
    else:
        checks.append(Check("model", False, f"run: ollama pull {name}"))
    return checks


def run_checks(model: str, host: str, db_path: Path) -> list[Check]:
    """Run every setup check, in a fixed order."""
    checks: list[Check] = []
    # Ensure host has a protocol prefix (OLLAMA_HOST often set as 0.0.0.0:11434)
    if "://" not in host:
        host = "http://" + host
    if model.startswith("ollama/"):
        checks.extend(_ollama_checks(model, host))

    bwrap = shutil.which("bwrap")
    if bwrap:
        checks.append(Check("bwrap", True, bwrap))
    else:
        checks.append(
            Check("bwrap", False, "bwrap not found: install bubblewrap for the kernel sandbox")
        )

    try:
        declared = load_declared()
        checks.append(Check("providers", True, f"{len(declared)} declared"))
    except Exception as exc:
        checks.append(Check("providers", False, f"providers.yaml: {exc}"))

    try:
        store = SQLiteStore(db_path)
        store.close()
        checks.append(Check("db", True, str(db_path)))
    except Exception as exc:
        checks.append(Check("db", False, f"cannot open {db_path}: {exc}"))

    return checks
