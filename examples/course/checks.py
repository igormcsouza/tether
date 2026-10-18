"""Deterministic gates. The model decides WHAT the course contains; code only checks facts."""

import re
import sys


def read(p):
    try:
        return open(p, encoding="utf-8").read()
    except FileNotFoundError:
        return ""


def plan():
    mods = []
    for line in read("plan.md").splitlines():
        if line.startswith("## Módulo"):
            mods.append({"title": line[3:].strip(), "topics": []})
        elif line.startswith("- ") and mods:
            mods[-1]["topics"].append(line[2:].strip())
    return mods


def refs():
    return [f"{i}.{j}" for i, m in enumerate(plan(), 1) for j, _ in enumerate(m["topics"], 1)]


def saved():
    return {r.split(" | ")[0] for r in read("videos.md").splitlines() if " | " in r}


def urls(text):
    return set(re.findall(r"https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}", text))


def fail(msg):
    print(msg)
    sys.exit(1)


what = sys.argv[1]
mods = plan()
if what == "plan":
    if not 1 <= len(mods) <= 3:
        fail(
            f"plan.md has {len(mods)} modules; the course needs 1 to 3 lines like `## Módulo 1: título`. edit write REPLACES the whole file: rewrite the COMPLETE plan in ONE edit write."
        )
    for i, m in enumerate(mods, 1):
        if not m["topics"]:
            fail(f"module {i} has no topics; list each topic on its own line starting with `- `.")
elif what == "videos":
    if not mods:  # fail closed: a missing plan.md must not pass
        fail("plan.md is missing or has no modules; run the planner first.")
    left = [r for r in refs() if r not in saved()]
    if left:
        fail(
            "topics without a video: "
            + ", ".join(left)
            + ". Use yt-todo, yt-candidates <ref>, yt-save <n>."
        )
elif what == "course":
    text, have = read("course.md"), urls(read("videos.md"))
    if not text.strip():
        fail("course.md is empty or missing: write it with edit write course.md.")
    foreign = urls(text) - have
    if foreign:
        fail(
            "course.md has links that are not in videos.md (invented): "
            + ", ".join(sorted(foreign))
            + ". Use only the VIDEO links from course-source."
        )
    missing = have - urls(text)
    if missing:
        lines = [r.split(" | ") for r in read("videos.md").splitlines()]
        todo = [f"- {p[2]}: {p[3]}" for p in lines if len(p) >= 4 and p[3] in missing]
        fail(
            f"{len(missing)} chosen videos are missing from course.md. Add each to its module's part-N.md (edit write replaces the file, so rewrite the whole part), run course-build, then done:\n"
            + "\n".join(todo)
        )
