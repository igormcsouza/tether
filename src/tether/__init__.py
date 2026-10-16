"""Tether: General-purpose, headless-first LLM-Native micro-harness."""

from __future__ import annotations

from tether.decorator import ToolSpec, tool
from tether.harness import Harness
from tether.sandbox import SandboxPolicy, SandboxViolationError
from tether.skills import Skill, SkillLoader
from tether.store import SessionRecord, SQLiteStore

__version__ = "0.1.0"

__all__ = [
    "Harness",
    "SQLiteStore",
    "SandboxPolicy",
    "SandboxViolationError",
    "SessionRecord",
    "Skill",
    "SkillLoader",
    "ToolSpec",
    "tool",
]
