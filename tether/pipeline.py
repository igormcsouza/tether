"""Declarative multi-stage deterministic pipelines and heterogeneous model routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from tether.store import SessionRecord, SQLiteStore


def _normalize_str_list(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [part.strip() for part in str(raw).split(",") if part.strip()]


@dataclass(slots=True)
class PipelineStage:
    """A single deterministic stage inside a multi-stage Tether pipeline."""

    id: str
    goal: str
    skill: str | None = None
    model: str | None = None
    tools: list[str] = field(default_factory=list)
    verify: list[str] = field(default_factory=list)
    sandbox: str | None = None
    max_steps: int | None = None

    def __post_init__(self) -> None:
        self.id = self.id.strip()
        self.goal = self.goal.strip()
        if not self.id:
            raise ValueError("PipelineStage `id` cannot be empty.")
        if not self.goal:
            raise ValueError(f"PipelineStage `{self.id}` goal cannot be empty.")
        if self.sandbox is not None and self.sandbox not in ("workspace-write", "read-only"):
            raise ValueError(f"Unsupported stage sandbox profile: {self.sandbox}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "skill": self.skill,
            "model": self.model,
            "tools": list(self.tools),
            "verify": list(self.verify),
            "sandbox": self.sandbox,
            "max_steps": self.max_steps,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 1) -> PipelineStage:
        stage_id = str(data.get("id") or f"stage_{index}").strip()
        goal = str(data.get("goal") or "").strip()
        skill = str(data["skill"]).strip() if data.get("skill") else None
        model = str(data["model"]).strip() if data.get("model") else None
        tools = _normalize_str_list(data.get("tools"))
        raw_verify = data.get("verify")
        if isinstance(raw_verify, list):
            verify = [str(v).strip() for v in raw_verify if str(v).strip()]
        elif raw_verify:
            verify = [str(raw_verify).strip()]
        else:
            verify = []
        sandbox = str(data["sandbox"]).strip() if data.get("sandbox") else None
        max_steps = int(data["max_steps"]) if data.get("max_steps") is not None else None
        return cls(
            id=stage_id,
            goal=goal,
            skill=skill,
            model=model,
            tools=tools,
            verify=verify,
            sandbox=sandbox,
            max_steps=max_steps,
        )


@dataclass(slots=True)
class Pipeline:
    """Declarative multi-stage workflow with isolated sessions and bounded FTS5 handoffs."""

    name: str
    stages: list[PipelineStage]
    description: str = ""
    sandbox: str | None = None
    max_steps: int | None = None

    def __post_init__(self) -> None:
        self.name = self.name.strip() or "pipeline"
        if not self.stages:
            raise ValueError(f"Pipeline `{self.name}` must define at least one stage.")
        seen_ids: set[str] = set()
        for st in self.stages:
            if st.id in seen_ids:
                raise ValueError(f"Duplicate stage id `{st.id}` in pipeline `{self.name}`.")
            seen_ids.add(st.id)
        if self.sandbox is not None and self.sandbox not in ("workspace-write", "read-only"):
            raise ValueError(f"Unsupported pipeline sandbox profile: {self.sandbox}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "sandbox": self.sandbox,
            "max_steps": self.max_steps,
            "stages": [s.to_dict() for s in self.stages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], default_name: str = "pipeline") -> Pipeline:
        name = str(data.get("name") or default_name).strip()
        description = str(data.get("description") or "").strip()
        sandbox = str(data["sandbox"]).strip() if data.get("sandbox") else None
        max_steps = int(data["max_steps"]) if data.get("max_steps") is not None else None
        raw_stages = data.get("stages")
        if not isinstance(raw_stages, list) or not raw_stages:
            raise ValueError(f"Pipeline `{name}` must contain a non-empty `stages` list.")
        stages: list[PipelineStage] = []
        for idx, raw_stage in enumerate(raw_stages, start=1):
            if not isinstance(raw_stage, dict):
                raise ValueError(f"Stage #{idx} in pipeline `{name}` must be a mapping.")
            stages.append(PipelineStage.from_dict(raw_stage, index=idx))
        return cls(
            name=name,
            stages=stages,
            description=description,
            sandbox=sandbox,
            max_steps=max_steps,
        )

    @classmethod
    def from_yaml(cls, raw_yaml: str, default_name: str = "pipeline") -> Pipeline:
        loaded = yaml.safe_load(raw_yaml)
        if not isinstance(loaded, dict):
            raise ValueError("Pipeline YAML manifest must parse to a top-level mapping.")
        return cls.from_dict(loaded, default_name=default_name)

    @classmethod
    def load(cls, path: str | Path) -> Pipeline:
        file_path = Path(path).resolve()
        raw_text = file_path.read_text(encoding="utf-8")
        return cls.from_yaml(raw_text, default_name=file_path.stem)


PipelineSpec = Pipeline


def parse_pipeline_yaml(raw_yaml: str, default_name: str = "pipeline") -> Pipeline:
    """Parse a YAML string into a validated `Pipeline` specification."""
    return Pipeline.from_yaml(raw_yaml, default_name=default_name)


def load_pipeline(path: str | Path) -> Pipeline:
    """Load a declarative YAML pipeline manifest from disk."""
    return Pipeline.load(path)


def render_stage_goal(
    stage: PipelineStage,
    root_goal: str,
    upstream_stages: list[tuple[str, SessionRecord]],
    store: SQLiteStore,
) -> str:
    """Render stage goal with `{{goal}}` interpolation and compact ~50-token upstream digests."""
    has_goal_placeholder = "{{goal}}" in stage.goal
    rendered = stage.goal.replace("{{goal}}", root_goal)
    for up_id, up_rec in upstream_stages:
        rendered = rendered.replace(f"{{{{{up_id}.session_id}}}}", up_rec.id)
        rendered = rendered.replace(f"{{{{{up_id}.id}}}}", up_rec.id)

    sections: list[str] = [rendered]
    if not has_goal_placeholder and root_goal.strip():
        sections.append(f"[Pipeline Goal]: {root_goal.strip()}")

    if upstream_stages:
        digest_lines = ["[Upstream Pipeline Stages]:"]
        for up_id, up_rec in upstream_stages:
            digest = store.get_session_digest(up_rec.id)
            digest_lines.append(f"- stage `{up_id}` (session `{up_rec.id}`):\n{digest}")
        sections.append("\n".join(digest_lines))

    return "\n\n".join(sections)
