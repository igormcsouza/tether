"""Progressive Skill discovery, YAML frontmatter parser, and companion tools.py loader."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from tether.decorator import ToolSpec, build_tool_spec
from tether.multiplexer import Multiplexer


@dataclass(slots=True)
class Skill:
    name: str
    description: str
    instructions: str
    model: str | None = None
    tools: list[str] = field(default_factory=list)
    verify: list[str] = field(default_factory=list)
    path: Path | None = None
    custom_tools: list[ToolSpec] = field(default_factory=list)


def parse_skill_markdown(
    raw_text: str, default_name: str, source_path: Path | None = None
) -> Skill:
    """Parse a Markdown file with optional YAML frontmatter into a Skill object."""
    text = raw_text.strip()
    meta: dict[str, Any] = {}
    body = text

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            yaml_block = parts[1].strip()
            body = parts[2].strip()
            loaded = yaml.safe_load(yaml_block)
            if isinstance(loaded, dict):
                meta = loaded

    name = str(meta.get("name") or default_name).strip()
    desc = str(meta.get("description") or f"Skill {name}").strip()
    model = str(meta["model"]).strip() if meta.get("model") else None
    raw_tools = meta.get("tools") or []
    tools_list = (
        [str(t).strip() for t in raw_tools]
        if isinstance(raw_tools, list)
        else [t.strip() for t in str(raw_tools).split(",") if t.strip()]
    )
    raw_verify = meta.get("verify") or []
    verify_list = (
        [str(v).strip() for v in raw_verify if str(v).strip()]
        if isinstance(raw_verify, list)
        else [str(raw_verify).strip()]
        if str(raw_verify).strip()
        else []
    )

    custom_tools: list[ToolSpec] = []
    if source_path and source_path.name == "SKILL.md":
        tools_py = source_path.parent / "tools.py"
        if tools_py.is_file():
            custom_tools = _load_tools_module(tools_py)

    return Skill(
        name=name,
        description=desc,
        instructions=body,
        model=model,
        tools=tools_list,
        verify=verify_list,
        path=source_path,
        custom_tools=custom_tools,
    )


def _load_tools_module(tools_py: Path) -> list[ToolSpec]:
    """Dynamically import a skill's sibling `tools.py` and extract `@tool` functions."""
    spec = importlib.util.spec_from_file_location(f"tether_skill_{tools_py.parent.name}", tools_py)
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    found: list[ToolSpec] = []
    for attr_name in dir(module):
        obj = getattr(module, attr_name)
        if hasattr(obj, "__tether_tool__"):
            t_spec: ToolSpec = obj.__tether_tool__
            found.append(t_spec)
    return found


class SkillLoader:
    """Discovers and loads skills from `./skills/` and `~/.tether/skills/`."""

    def __init__(self, search_dirs: list[str | Path] | None = None) -> None:
        if search_dirs is not None:
            self.search_dirs = [Path(d).resolve() for d in search_dirs]
        else:
            self.search_dirs = [
                (Path.cwd() / "skills").resolve(),
                (Path.home() / ".tether" / "skills").resolve(),
            ]

    def discover(self) -> dict[str, Skill]:
        skills: dict[str, Skill] = {}
        for base in self.search_dirs:
            if not base.is_dir():
                continue
            # 1. Single-file skills: skills/<name>.md
            for md_file in sorted(base.glob("*.md")):
                default_name = md_file.stem
                sk = parse_skill_markdown(
                    md_file.read_text(encoding="utf-8"), default_name, md_file
                )
                skills.setdefault(sk.name, sk)
            # 2. Directory skills: skills/<name>/SKILL.md
            for skill_md in sorted(base.glob("*/SKILL.md")):
                default_name = skill_md.parent.name
                sk = parse_skill_markdown(
                    skill_md.read_text(encoding="utf-8"), default_name, skill_md
                )
                skills.setdefault(sk.name, sk)
        return skills

    def load(self, name: str) -> Skill | None:
        return self.discover().get(name)


def make_skill_tool(loader: SkillLoader, mux: Multiplexer) -> ToolSpec:
    """Create the progressive `skill` tool (`skill list | load <name>`)."""
    help_str = (
        "Usage: skill list | skill load <name>\n"
        "Desc : List available skills or load a skill's instructions and tools."
    )

    def _dispatch(args: list[str], stdin: str | None = None) -> str:
        if not args or args[0] in ("--help", "-h"):
            return help_str
        sub = args[0]
        if sub == "list":
            discovered = loader.discover()
            if not discovered:
                return "No skills found in ./skills/ or ~/.tether/skills/."
            return "\n".join(f"- {s.name}: {s.description}" for s in discovered.values())
        if sub == "load":
            if len(args) < 2:
                return f"Error: missing `<name>`.\n{help_str}"
            sk = loader.load(args[1])
            if not sk:
                return f"Error: skill `{args[1]}` not found."
            for ct in sk.custom_tools:
                mux.register(ct)
            return f"[Skill `{sk.name}` loaded]\n{sk.instructions}"
        return f"Error: unknown subcommand `{sub}`.\n{help_str}"

    return build_tool_spec(
        _dispatch,
        name="skill",
        description="Discover and load specialized skills",
        custom_help=help_str,
        raw_dispatch=True,
    )
