"""Failure breakdown for a results dir: `python3 bench/report.py <out> [<out> ...]`.

Splits every run into pass, model-side outcomes (wrong answer, ran out of steps, stalled) and
failures that say nothing about the harness's logic (provider outage, killed by timeout), so a
score never hides infrastructure noise and infrastructure never hides a harness bug.
"""
import collections
import json
import os
import re
import sys

OUTAGE = re.compile(r"unavailable after|429|503|Not Found|ConnectError|TimeoutError")


def outcome(r):
    if r["pass"]:
        return "pass"
    try:
        j = json.loads(open(r["dir"] + "/stdout.txt").read())
    except (OSError, ValueError):
        return "timeout" if r.get("run_status") == "timeout" else "no_output"
    f = j.get("failure") or {}
    kind, msg = f.get("kind"), f.get("message", "")
    if kind == "worker_error":
        return "outage" if OUTAGE.search(msg) else "worker_error"
    return kind or ("wrong_answer" if j.get("status") == "COMPLETED" else "timeout")


def main(dirs):
    rows = []
    for d in dirs:
        rows += [json.loads(line) for line in open(os.path.join(d, "results.jsonl"))]
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(r["runner"], r["model"])].append(r)
    for (runner, model), rs in sorted(groups.items()):
        c = collections.Counter(outcome(r) for r in rs)
        valid = [r for r in rs if outcome(r) not in ("outage", "timeout", "no_output")]
        mean = lambda l: round(sum(x["score"] for x in l) / len(l), 3) if l else 0.0  # noqa: E731
        wall = round(sum(r["wall_s"] for r in rs) / len(rs))
        print(f"{runner} {model}: {len(rs)} runs, pass {c['pass']} ({c['pass'] / len(rs):.0%}), mean {mean(rs)}, "
              f"mean over valid runs {mean(valid)}, {wall}s/run")
        print("   " + ", ".join(f"{k} {v}" for k, v in c.most_common()))


if __name__ == "__main__":
    main(sys.argv[1:])
