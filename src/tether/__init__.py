"""Tether: General-purpose, headless-first LLM-Native micro-harness."""

from __future__ import annotations

from tether.decorator import ToolSpec, tool
from tether.harness import Harness
from tether.providers import (
    ActionCall,
    ModelProvider,
    ModelResponse,
    extract_fallback_action,
    register_provider,
)
from tether.sandbox import SandboxPolicy, SandboxViolationError
from tether.skills import Skill, SkillLoader
from tether.store import SessionRecord, SQLiteStore

__version__ = "0.0.2"

__all__ = [
    "ActionCall",
    "Harness",
    "ModelProvider",
    "ModelResponse",
    "SQLiteStore",
    "SandboxPolicy",
    "SandboxViolationError",
    "SessionRecord",
    "Skill",
    "SkillLoader",
    "ToolSpec",
    "extract_fallback_action",
    "register_provider",
    "tool",
]
