"""Tether: General-purpose, headless-first LLM-Native micro-harness."""

from __future__ import annotations

from tether.decorator import ToolSpec, tool
from tether.harness import Harness
from tether.providers import (
    ActionCall,
    ModelProvider,
    ModelResponse,
    ProviderResponse,
    extract_fallback_action,
    register_provider,
)
from tether.sandbox import SandboxPolicy, SandboxViolationError
from tether.skills import Skill, SkillLoader
from tether.store import (
    GLOBAL_SESSION_ID,
    ModelStats,
    SessionRecord,
    SQLiteStore,
    StatsReport,
    ToolOffender,
)

__version__ = "0.0.3"

__all__ = [
    "ActionCall",
    "GLOBAL_SESSION_ID",
    "Harness",
    "ModelProvider",
    "ModelResponse",
    "ModelStats",
    "ProviderResponse",
    "SQLiteStore",
    "SandboxPolicy",
    "SandboxViolationError",
    "SessionRecord",
    "Skill",
    "SkillLoader",
    "StatsReport",
    "ToolOffender",
    "ToolSpec",
    "extract_fallback_action",
    "register_provider",
    "tool",
]
