"""Export a stored tether session as a golden-trace fixture (`tests/golden/<name>.json`).

    python scripts/record_golden.py <db> <session_id> <out.json> [--stub web,agent]

Model steps come from the assistant turns; observations of the `--stub` tools (network ones)
are kept as ordered stub outputs so the replay never touches the network. Trim or sanitise
anything private before committing the fixture.
"""

from __future__ import annotations

import json
import sqlite3
import sys

db, sid, out, *rest = sys.argv[1:]
stub_names = rest[1].split(",") if rest[:1] == ["--stub"] else ["web"]
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
goal, tools = c.execute("select goal, tools_json from sessions where id=?", (sid,)).fetchone()
steps = [
    {"content": content, **({"cmd": cmd} if cmd else {}), **({"stdin": stdin} if stdin else {})}
    for content, cmd, stdin in c.execute(
        "select content, tool_cmd, tool_stdin from turns "
        "where session_id=? and role='assistant' order by id",
        (sid,),
    )
]
stubs: dict[str, list[str]] = {n: [] for n in stub_names}
for cmd, raw in c.execute(
    "select cmd, raw_output from observations where session_id=? order by rowid", (sid,)
):
    first = (cmd.split()[1:2] if cmd.startswith("bash ") else cmd.split()[:1]) or [""]
    if first[0] in stubs:
        stubs[first[0]].append(raw)
fixture = {
    "goal": goal,
    "tools": [t for t in json.loads(tools) if t not in stubs],
    "stubs": {n: o for n, o in stubs.items() if o},
    "phases": [{"steps": steps}],
}
open(out, "w").write(json.dumps(fixture, indent=1) + "\n")
print(f"{out}: {len(steps)} steps, stubs { {n: len(o) for n, o in stubs.items()} }")
