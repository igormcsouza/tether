"""Deterministic helpers: read one module's plan+videos at a time, and assemble the parts into course.md."""

import glob
import re

from tether import tool


def _read(p):
    try:
        return open(p, encoding="utf-8").read()
    except FileNotFoundError:
        return ""


def _modules():
    """[(title_line, [lines])] for each '## Módulo' block of plan.md."""
    vids = {}
    for row in _read("videos.md").splitlines():
        p = row.split(" | ")
        if len(p) >= 5:
            vids[p[0]] = f"    VIDEO: {p[2]} | {p[3]} | canal {p[4]}"
    mods, t = [], 0
    for line in _read("plan.md").splitlines():
        if line.startswith("## Módulo"):
            mods.append((line, []))
            t = 0
        elif mods and line.startswith("- "):
            t += 1
            mods[-1][1].append(line)
            if f"{len(mods)}.{t}" in vids:
                mods[-1][1].append(vids[f"{len(mods)}.{t}"])
        elif mods and line.strip():
            mods[-1][1].append(line)
    return mods


@tool(name="course-source", description="Plan and chosen videos: list modules, or show module N")
def course_source(module: str = "") -> str:
    """Without MODULE: the list of modules. With MODULE (number): its objective, topics and each topic's VIDEO."""
    mods = _modules()
    if not module.strip():
        return (
            "Modules:\n"
            + "\n".join(f"{i}. {t[3:]}" for i, (t, _) in enumerate(mods, 1))
            + "\nNext: course-source <n> then edit write part-<n>.md"
        )
    try:
        title, lines = mods[int(module) - 1]
    except (ValueError, IndexError):
        return f"no such module; use 1 to {len(mods)}"
    return "\n".join([title] + lines) + (
        f'\n\nNOW WRITE THIS MODULE (do not read anything else): act("edit write part-{int(module)}.md", stdin="## Módulo ...")'
        + (
            f'. Then act("course-source {int(module) + 1}").'
            if int(module) < len(mods)
            else '. Then act("course-build"), then act("done", stdin="curso pronto").'
        )
    )


@tool(name="course-build", description="Join part-*.md into course.md")
def course_build() -> str:
    """Concatenate part-1.md, part-2.md, ... in numeric order into course.md."""
    parts = sorted(glob.glob("part-*.md"), key=lambda p: int(re.findall(r"\d+", p)[0]))
    if not parts:
        return "no part-N.md files yet; write one per module with edit write part-<n>.md"
    open("course.md", "w", encoding="utf-8").write(
        "\n\n".join(_read(p).strip() for p in parts) + "\n"
    )
    return f"course.md built from {len(parts)} parts"
