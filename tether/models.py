"""`tether models`: list the model ids tether can use (#310)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from tether.providers import _CUSTOM_PROVIDERS
from tether.providers.declarative import load_declared

# built-in prefix -> (key env var or "", default model or "")
BUILTIN: dict[str, tuple[str, str]] = {
    "ollama": ("", "qwen3.5:9b"),
    "openai": ("OPENAI_API_KEY", ""),
    "anthropic": ("ANTHROPIC_API_KEY", ""),
    "claude": ("ANTHROPIC_API_KEY", ""),
}


def _key(env: str) -> dict[str, Any]:
    return {"key_env": env, "key_set": bool(os.environ.get(env))} if env else {}


def collect(host: str) -> dict[str, Any]:
    """Everything tether can reach, as the `--json` document (without the `v` key).

    Raises ValueError (`providers.yaml: ...`) when providers.yaml is invalid.
    """
    if "://" not in host:
        host = "http://" + host
    declared = load_declared()
    try:
        resp = httpx.get(f"{host}/api/tags", timeout=2)
        resp.raise_for_status()
        ollama: dict[str, Any] = {
            "host": host,
            "reachable": True,
            "models": [f"ollama/{m['name']}" for m in resp.json().get("models", [])],
        }
    except Exception as exc:
        ollama = {"host": host, "reachable": False, "models": [], "error": str(exc)}
    return {
        "ollama": ollama,
        "providers": [
            {"prefix": name, "kind": cfg["kind"], **_key(cfg.get("api_key_env", ""))}
            for name, cfg in declared.items()
        ],
        "builtin": [
            {"prefix": p, **_key(env), **({"default": f"{p}/{d}"} if d else {})}
            for p, (env, d) in BUILTIN.items()
        ],
        "registered": sorted(_CUSTOM_PROVIDERS),
    }


def _key_text(item: dict[str, Any]) -> str:
    if "key_env" not in item:
        return ""
    return f"  {item['key_env']}: {'set' if item['key_set'] else 'not set'}"


def render(data: dict[str, Any]) -> str:
    """The plain-text listing: one model id or `<prefix>/<model>` pattern per line."""
    o = data["ollama"]
    lines = [f"ollama ({o['host']})"]
    if o["reachable"]:
        lines += [f"  {m}" for m in o["models"]] or ["  (no models pulled: ollama pull <model>)"]
    else:
        lines.append("  not reachable: start Ollama or set OLLAMA_HOST")
    if data["providers"]:
        lines.append("providers.yaml")
        lines += [
            f"  {p['prefix']}/<model>  kind={p['kind']}{_key_text(p)}" for p in data["providers"]
        ]
    lines.append("built-in")
    for b in data["builtin"]:
        lines.append(f"  {b['prefix']}/<model>{_key_text(b)}")
        if "default" in b:
            lines[-1] += f"  default: {b['default']}"
    if data["registered"]:
        lines.append("registered")
        lines += [f"  {p}/<model>" for p in data["registered"]]
    return "\n".join(lines)
