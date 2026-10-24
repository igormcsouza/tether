"""Tether: General-purpose, headless-first LLM-Native micro-harness."""

from __future__ import annotations

from tether.decorator import ToolSpec, tool
from tether.harness import Harness
from tether.multiplexer import register_normalizer
from tether.pipeline import (
    Pipeline,
    PipelineSpec,
    PipelineStage,
    load_pipeline,
    parse_pipeline_yaml,
)
from tether.providers import (
    ActionCall,
    ModelProvider,
    ModelResponse,
    ProviderResponse,
    extract_fallback_action,
    register_dialect,
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

__version__ = "0.2.7"

__all__ = [
    "ActionCall",
    "GLOBAL_SESSION_ID",
    "Harness",
    "ModelProvider",
    "ModelResponse",
    "ModelStats",
    "Pipeline",
    "PipelineSpec",
    "PipelineStage",
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
    "load_pipeline",
    "parse_pipeline_yaml",
    "register_dialect",
    "register_normalizer",
    "register_provider",
    "tool",
]
