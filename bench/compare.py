"""Paired A/B of two bench runs: `python3 bench/compare.py <before-dir> <after-dir>`.

A pass rate over 68 runs has a standard error of ~6 points and 10 of 34 exercises carry all the
flips, so "35/68 vs 35/68" or "9/20 vs 6/20" cannot tell a change from luck. This reports what can:
the paired per-run score delta with a bootstrap 95% CI resampled over exercises (runs of one
exercise are not independent), the up/down flips with an exact sign test, and the mechanism numbers
(wall-cap rate, steps, empty turns) that move before the pass rate does.

Verdict: BETTER / WORSE when the score CI excludes 0, else NO EVIDENCE with the number of paired
runs it would take to see the observed delta (a delta of ~0 reports "no effect detectable").
"""

import json
import math
import random
import statistics as st
import sys
from collections import defaultdict


def load(path):
    rows = defaultdict(dict)
    for line in open(f"{path}/results.jsonl"):
        r = json.loads(line)
        rows[r["task"]][r["trial"]] = r
    return rows


def sign_p(up, down):
    n = up + down
    if n == 0:
        return 1.0
    k = min(up, down)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n)


def mean_delta(by_task):
    ds = [d for v in by_task.values() for d in v]
    return st.mean(ds) if ds else 0.0


def compare(a, b, boot=4000, seed=1):
    tasks = sorted(set(a) & set(b))
    by_task, up, down, pairs = {}, 0, 0, 0
    for t in tasks:
        ds = []
        for i in set(a[t]) & set(b[t]):
            ra, rb = a[t][i], b[t][i]
            ds.append(rb["score"] - ra["score"])
            up += (not ra["pass"]) and rb["pass"]
            down += ra["pass"] and not rb["pass"]
            pairs += 1
        if ds:
            by_task[t] = ds
    rng, keys, means = random.Random(seed), list(by_task), []
    for _ in range(boot):
        pick = [by_task[rng.choice(keys)] for _ in keys]
        means.append(mean_delta(dict(enumerate(pick))))
    means.sort()
    lo, hi = means[int(0.025 * boot)], means[int(0.975 * boot) - 1]
    return by_task, pairs, up, down, lo, hi


def mech(rows, tasks):
    rs = [r for t in tasks for r in rows[t].values()]
    n = len(rs)
    empty = sum(r["events"].count("nudge") if isinstance(r["events"], list) else r["events"].get("nudge", 0) for r in rs)
    return {
        "runs": n,
        "pass": sum(r["pass"] for r in rs) / n,
        "score": st.mean(r["score"] for r in rs),
        "wall_cap": sum(r.get("run_status") == "timeout" for r in rs) / n,
        "steps": st.mean(r["steps"] for r in rs),
        "wall_s": st.mean(r["wall_s"] for r in rs),
        "nudges/run": empty / n,
    }


def main(pa, pb):
    a, b = load(pa), load(pb)
    by_task, pairs, up, down, lo, hi = compare(a, b)
    tasks = list(by_task)
    delta = mean_delta(by_task)
    print(f"{len(tasks)} exercises, {pairs} paired runs")
    ma, mb = mech(a, tasks), mech(b, tasks)
    for k in ma:
        fa, fb = ma[k], mb[k]
        print(f"  {k:11} {fa:8.3f} -> {fb:8.3f}")
    print(f"score delta {delta:+.3f}  95% CI [{lo:+.3f}, {hi:+.3f}]  (bootstrap over exercises)")
    print(f"pass flips +{up} / -{down}  sign test p={sign_p(up, down):.2f}")
    if lo > 0:
        print("verdict: BETTER")
    elif hi < 0:
        print("verdict: WORSE")
    else:
        sd = st.pstdev([d for v in by_task.values() for d in v]) or 1e-9
        need = int(math.ceil((1.96 * sd / max(abs(delta), 1e-3)) ** 2)) if delta else 0
        print(f"verdict: NO EVIDENCE (CI spans 0)" + (f"; ~{need} paired runs to resolve {delta:+.3f}" if need else ""))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
