"""15-minute check: did this change help? `python3 bench/canary.py <out-dir> [--tether-bin ...]`.

Runs 7 Polyglot exercises once (4 flaky ones that can flip, 3 fast guards), then compares each
score with the pinned baseline (`canary_baseline.json`, mean of 2 runs on main@b25cbbe).
Verdict: REJECT if a guard drops >0.2, PROMISING if the flaky mean gains >=0.1, else FLAT.
Only PROMISING changes earn a full 34x2 run. One run per exercise is noisy: a FLAT verdict
means "no evidence", not "proven useless".
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import grade  # noqa: E402


def main(out, extra):
    cmd = [sys.executable, f"{HERE}/run.py", "--models", "ollama/qwen3.5:9b", "--tasks", "canary",
           "--poly-verify", "--par", "ollama=1", "--out", out, *extra]
    subprocess.run(cmd, check=True)
    base = json.load(open(f"{HERE}/canary_baseline.json"))
    now = {}
    for line in open(f"{out}/results.jsonl"):
        r = json.loads(line)
        now[r["task"][5:]] = r["score"]
    flaky = [e for e in base if e not in grade.GUARDS]
    for e in base:
        print(f"{e:20} {base[e]:.2f} -> {now.get(e, float('nan')):.2f}{'  (guard)' if e in grade.GUARDS else ''}")
    gain = sum(now.get(e, 0) - base[e] for e in flaky) / len(flaky)
    drops = [e for e in grade.GUARDS if now.get(e, 0) < base[e] - 0.2]
    verdict = "REJECT" if drops else "PROMISING" if gain >= 0.1 else "FLAT"
    print(f"flaky mean delta {gain:+.2f}; guard drops {drops or 'none'} -> {verdict}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
