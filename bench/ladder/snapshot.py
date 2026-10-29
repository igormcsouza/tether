"""Freeze ladder results into the committed baseline: `python3 bench/ladder/snapshot.py <ladder-dir>[:model,...]... <label>=<harness-dir>...`.

Keeps only what the docs charts and the comparison need, so the baseline stays a few hundred KB and
diffable. Writes `bench/ladder/baseline/ladder.jsonl` (tier climbs) and `harness.jsonl` (every task
once per harness). Model aliases created for context size (`qwen3.5-9b-40k`) map back to the real name.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ALIAS = {"qwen3.5-9b-40k": "qwen3.5:9b", "qwen3.5-4b-40k": "qwen3.5:4b", "qwen2.5-coder-7b-32k": "qwen2.5-coder:7b"}
KEEP = ("model", "harness", "label", "task", "kind", "tier", "attempt", "think", "ctx", "wall_s", "score", "pass",
        "steps", "delivered_steps", "prompt_tokens", "completion_tokens", "run_status", "session_status")


def rows(path, label=None, only=None):
    out = []
    for line in open(os.path.join(path, "results.jsonl")):
        r = json.loads(line)
        r["model"] = ALIAS.get(r["model"], r["model"])
        if only and r["model"] not in only:
            continue
        r["harness"] = r.get("harness", "tether")
        r["label"] = label or r["harness"]
        out.append({k: r.get(k) for k in KEEP})
    return out


def main(argv):
    ladders = [a for a in argv if "=" not in a]
    harness = [a.split("=", 1) for a in argv if "=" in a]  # a label may repeat across models
    os.makedirs(f"{HERE}/baseline", exist_ok=True)
    with open(f"{HERE}/baseline/ladder.jsonl", "w") as fh:
        for spec in ladders:  # dir or dir:model,model (the first 7b ladder predates the tool-call fixes)
            d, _, only = spec.partition(":")
            for r in rows(d, only=only.split(",") if only else None):
                fh.write(json.dumps(r) + "\n")
    with open(f"{HERE}/baseline/harness.jsonl", "w") as fh:
        for label, d in harness:
            for r in rows(d, label):
                fh.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
