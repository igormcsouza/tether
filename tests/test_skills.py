"""Unit tests for tether/skills.py (SkillLoader, YAML frontmatter, tools.py, skill CLI tool)."""

from __future__ import annotations

from pathlib import Path

from tether import Harness, SandboxPolicy, SkillLoader
from tether.multiplexer import Multiplexer
from tether.skills import _load_tools_module, make_skill_tool


async def test_skill_loader_and_companion_tools(tmp_path: Path) -> None:
    """Verify SkillLoader with directory SKILL.md, single-file .md, and sibling tools.py."""
    skill_dir = tmp_path / "skills" / "analyst"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: analyst\n"
        "description: Financial ratio calculator\n"
        "model: ollama/qwen3.5:9b\n"
        "tools: [edit, calc-margin]\n"
        "---\n"
        "Use calc-margin and write results.",
        encoding="utf-8",
    )
    (skill_dir / "tools.py").write_text(
        "from tether import tool\n\n"
        "@tool(name='calc-margin', description='Compute profit margin percentage')\n"
        "def calc_margin(revenue: float, cost: float) -> str:\n"
        "    return f'{((revenue - cost) / revenue) * 100:.1f}%'\n",
        encoding="utf-8",
    )

    loader = SkillLoader(search_dirs=[tmp_path / "skills"])
    sk = loader.load("analyst")
    assert sk is not None
    assert sk.model == "ollama/qwen3.5:9b"
    assert len(sk.custom_tools) == 1

    harness = Harness(
        db_path=tmp_path / "tether.db",
        skill=sk,
        sandbox=SandboxPolicy(workspace_root=tmp_path),
    )
    mux = harness.build_multiplexer(
        session_id="ses_skill",
        enabled_tools=sk.tools,
        sandbox=SandboxPolicy(workspace_root=tmp_path),
        model=sk.model,
    )
    res_calc = await mux.execute("calc-margin 200 50")
    assert res_calc.output == "75.0%"

    # Test skill CLI tool edge cases
    empty_loader = SkillLoader(search_dirs=[tmp_path / "empty_skills"])
    empty_mux = Multiplexer()
    empty_mux.register(make_skill_tool(empty_loader, empty_mux))
    assert "Usage: skill" in (await empty_mux.execute("skill --help")).output
    assert "No skills found" in (await empty_mux.execute("skill list")).output
    assert "Error: missing `<name>`" in (await empty_mux.execute("skill load")).output
    assert "not found" in (await empty_mux.execute("skill load nope")).output
    assert "Error: unknown subcommand" in (await empty_mux.execute("skill bogus")).output

    # Single-file skill + dynamic loading via `skill load`
    sk_dir = tmp_path / "my_skills"
    sk_dir.mkdir()
    (sk_dir / "quick.md").write_text(
        "---\nname: quick\ndescription: Quick skill\ntools: web, mem\n---\nInstructions here.",
        encoding="utf-8",
    )
    loader2 = SkillLoader(search_dirs=[sk_dir, tmp_path / "skills"])
    sk_mux = Multiplexer()
    sk_mux.register(make_skill_tool(loader2, sk_mux))
    assert "quick: Quick skill" in (await sk_mux.execute("skill list")).output
    assert "[Skill `quick` loaded]" in (await sk_mux.execute("skill load quick")).output
    assert "[Skill `analyst` loaded]" in (await sk_mux.execute("skill load analyst")).output
    assert sk_mux.get_tool("calc-margin") is not None

    assert _load_tools_module(tmp_path / "nonexistent_file.xyz") == []
    assert SkillLoader().search_dirs
