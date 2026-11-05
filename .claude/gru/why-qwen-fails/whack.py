"""whack.py <run dir>...: between consecutive test runs, how often a change fixes some tests and breaks others."""

import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

FAILNAME = re.compile(r"^(?:FAIL|ERROR): (\w+)", re.M)
SUMMARY = re.compile(r"Ran (\d+) tests?.*?(OK|FAILED)", re.S)
c = Counter()
for base in map(Path, sys.argv[1:]):
    for run in sorted(base.glob("tether__*")):
        ok = json.loads((run / "done.json").read_text())["pass"]
        db = sqlite3.connect(run / "t.db")
        sets, pend = [], False
        for role, cmd, content in db.execute("select role, tool_cmd, content from turns order by id"):
            if role == "assistant":
                pend = bool(re.search(r"unittest|pytest", cmd or ""))
            elif role == "tool" and pend and SUMMARY.search(content or ""):
                sets.append(frozenset(FAILNAME.findall(content or "")))
        for a, b in zip(sets, sets[1:]):
            fixed, broke = a - b, b - a
            k = "fix+break" if fixed and broke else "fix only" if fixed else "break only" if broke else "no change"
            c[(ok, k)] += 1
for ok in (True, False):
    n = sum(v for (o, _), v in c.items() if o == ok)
    print("PASS" if ok else "FAIL", n, {k: f"{v} ({v / max(1, n):.0%})" for (o, k), v in sorted(c.items()) if o == ok})
