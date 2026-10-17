"""Offline post-mortem (`tether retro`): distill session friction into tiny Skill rules."""

from __future__ import annotations

import difflib
import re
import zlib

from tether.context import estimate_tokens
from tether.providers import ModelProvider, resolve_provider
from tether.skills import SkillLoader
from tether.store import GLOBAL_SESSION_ID, SQLiteStore

MAX_RULES = 2
MAX_RULE_TOKENS = 30
SECTION = "## Learned Rules"

_PROMPT = (
    f"Below is a failed-then-fixed agent trajectory. Write at most {MAX_RULES} imperative "
    f"bullet rules (`- ...`, under {MAX_RULE_TOKENS} tokens each) that would prevent these "
    "mistakes next time. Output only the bullets.\n\n"
)


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def parse_rules(text: str, existing: str = "") -> list[str]:
    """Keep <=MAX_RULES bullets within the token cap, dropping ones already in `existing`."""
    seen = {_norm(ln.lstrip("-* ")) for ln in existing.splitlines()}
    rules: list[str] = []
    for ln in text.splitlines():
        m = re.match(r"\s*[-*]\s+(.+)", ln)
        if not m:
            continue
        rule = m.group(1).strip()
        if estimate_tokens(rule) > MAX_RULE_TOKENS or _norm(rule) in seen:
            continue
        seen.add(_norm(rule))
        rules.append(rule)
    return rules[:MAX_RULES]


def append_rules(text: str, rules: list[str]) -> str:
    body = "\n".join(f"- {r}" for r in rules)
    if SECTION in text:
        return text.rstrip("\n") + "\n" + body + "\n"
    return text.rstrip("\n") + f"\n\n{SECTION}\n{body}\n"


async def run_retro(
    store: SQLiteStore,
    session_id: str,
    *,
    apply: bool = False,
    model: str | None = None,
    provider: ModelProvider | None = None,
) -> str:
    rec = store.get_session(session_id)
    if rec is None:
        raise ValueError(f"session `{session_id}` not found.")
    trace = store.extract_friction_trace(session_id)
    if not trace:
        return "No friction found; nothing to learn."

    skill = SkillLoader().load(rec.skill) if rec.skill else None
    path = skill.path if skill and skill.path else None
    current = path.read_text(encoding="utf-8") if path else ""
    existing = current or "\n".join(store.get_pins(GLOBAL_SESSION_ID).values())

    prov = provider or resolve_provider(model or rec.model)
    resp = await prov.generate([{"role": "user", "content": _PROMPT + "\n".join(trace)}], [])
    rules = parse_rules(resp.content, existing)
    if not rules:
        return "No new rules (none produced, over token cap, or duplicates)."

    if path is None:
        if apply:
            for r in rules:
                store.set_pin(GLOBAL_SESSION_ID, f"retro_{zlib.crc32(_norm(r).encode())}", r)
        return "\n".join(f"- {r}" for r in rules) + ("\n[pinned to project]" if apply else "")

    updated = append_rules(current, rules)
    if apply:
        path.write_text(updated, encoding="utf-8")
        return f"Applied {len(rules)} rule(s) to {path}"
    return "".join(
        difflib.unified_diff(
            current.splitlines(True), updated.splitlines(True), str(path), str(path)
        )
    )
