"""`python3 bench/ladder/report.py <out-dir>`: tier reached, time, score, steps, ctx per model and kind."""
import json
import sys
from collections import defaultdict

KINDS = ("write", "bugfix", "plan", "review")


def main(out):
    rows = [json.loads(l) for l in open(f"{out}/results.jsonl")]
    by = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by[(r.get("harness", "tether"), r["model"])][r["task"]].append(r)
    for (harness, model), tasks in by.items():
        ctx = next(iter(tasks.values()))[0]["ctx"]
        print(f"\n== {harness} / {model}  (context {ctx})")
        print(f"{'task':10} {'result':8} {'att':>3} {'think':>5} {'score':>5} {'time':>6} {'steps':>5} {'prompt tok':>10}  note")
        total_t = 0
        for kind in KINDS:
            reached = 0
            for tier in range(1, 7):
                rs = tasks.get(f"{kind}-{tier}")
                if not rs:
                    break
                best = max(rs, key=lambda r: (r["pass"], r["score"]))
                win = next((r for r in rs if r["pass"]), None)
                last = win or rs[-1]
                t = sum(r["wall_s"] for r in rs)
                total_t += t
                if win:
                    reached = tier
                note = ", ".join(f"a{r['attempt']}:{r['score']:.2f}" for r in rs) if len(rs) > 1 or not win else ""
                st = last.get("delivered_steps") or last.get("steps")
                print(f"{kind}-{tier:<4} {'PASS' if win else 'STUCK':8} {len(rs):>3} {'on' if last['think'] else 'off':>5} "
                      f"{best['score']:>5.2f} {t:>5}s {st if st is not None else '-':>5} {last.get('prompt_tokens', 0):>10}  {note}")
            print(f"  -> {kind}: tier {reached} reached")
        print(f"  total wall {total_t // 60} min")


if __name__ == "__main__":
    main(sys.argv[1])
