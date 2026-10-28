"""Coding ladder: 6 tiers x {write, bugfix, plan, review}, climbed per model until it gets stuck.

  python3 bench/ladder/run.py --out /tmp/ladder --models qwen3.5:9b,qwen3.5:4b,qwen2.5-coder:7b \
      --ctx qwen3.5:9b=40960,qwen3.5:4b=65536,qwen2.5-coder:7b=32768

Per (model, kind) the tiers are tried in order. A tier gets up to 4 attempts, stopping at the first
pass: (0) thinking off, (1) thinking on, (2) thinking on + more steps/later folding, (3) thinking
off, temperature 0, more steps/later folding. A tier that fails all 4 ends that kind's ladder: the
model never sees the next tier. Resumable: finished attempts are read back from results.jsonl.
"""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tasks as T  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

ATTEMPTS = [  # (think, extra params, max_steps, fold_after)
    (False, [], 30, None),
    (True, [], 30, None),
    (True, [], 50, 3),
    (False, ["temperature=0"], 50, 3),
]


def steps_now(rd):
    try:
        c = sqlite3.connect(f"file:{rd}/t.db?mode=ro", uri=True)
        return c.execute("select step_count from sessions order by created_at desc limit 1").fetchone()[0]
    except Exception:
        return None


def steps_other(harness, rd):
    """Tool-call count for a non-tether harness, from its own output."""
    try:
        if harness == "naive":
            return json.load(open(rd / "stats.json")).get("steps")
        text = (rd / "stdout.txt").read_text()
        if harness == "opencode":
            return sum('"type":"tool' in l.replace(" ", "") for l in text.splitlines())
        return json.loads(text[text.index("{"):]).get("num_turns")
    except Exception:
        return None


def capabilities(model):
    """Ollama capabilities of a model (`thinking`, `tools`, ...); empty when unknown."""
    import httpx
    try:
        r = httpx.post("http://localhost:11435/api/show", json={"model": model}, timeout=30)
        return r.json().get("capabilities", [])
    except Exception:
        return []


def harness_cmd(harness, model, task, ctx, rd, ws, tether_bin, think, can_think, params, steps, fold):
    if harness == "tether":
        cmd = [tether_bin, "run", "--model", f"ollama/{model}", "--tools", "edit,bash", "--max-steps", str(steps),
               "--context-tokens", str(ctx), "--db", str(rd / "t.db")]
        if can_think:  # a model without a thinking mode rejects the parameter
            cmd += ["--param", f"think={str(think).lower()}"]
        for p in params:
            cmd += ["--param", p]
        if fold:
            cmd += ["--fold-after", str(fold)]
        return cmd + [task.goal]
    if harness == "naive":  # plain tool loop, same model: what the model does without tether
        return [sys.executable, f"{HERE}/../naive_agent.py", "--base-url", "http://localhost:11435/v1",
                "--model", model, "--ws", str(ws), "--goal", task.goal, "--max-turns", str(steps),
                "--result-file", str(rd / "result.txt"), "--stats-file", str(rd / "stats.json")]
    if harness == "opencode":
        (Path(ws) / "opencode.json").write_text(json.dumps({"$schema": "https://opencode.ai/config.json", "provider": {
            "ollama": {"npm": "@ai-sdk/openai-compatible", "name": "Ollama", "options": {"baseURL": "http://localhost:11435/v1"},
                       "models": {model: {"name": model, "limit": {"context": ctx, "output": 8192}}}}}}))
        return [os.path.expanduser("~/.claude/skills/gru/sandbox.sh"), str(ws), "--", "opencode", "run", "--auto",
                "--format", "json", "-m", f"ollama/{model}", task.goal]
    if harness == "claude":  # Claude Code, print mode, the model alias is the part after cc/
        return ["env", "-u", "ANTHROPIC_API_KEY", "claude", "-p", task.goal, "--model", model.removeprefix("cc/"),
                "--permission-mode", "bypassPermissions", "--output-format", "json", "--setting-sources", "",
                "--disable-slash-commands", "--no-session-persistence", "--max-budget-usd", "1"]
    raise SystemExit(f"unknown harness {harness}")


def run_attempt(model, task, attempt, ctx, out, tether_bin, wall, can_think=True, harness="tether"):
    think, params, steps, fold = ATTEMPTS[attempt]
    rd = Path(out) / "runs" / f"{harness}__{model.replace(':', '-').replace('/', '_')}__{task.id}__a{attempt}"
    shutil.rmtree(rd, ignore_errors=True)
    ws = rd / "ws"
    for path, text in T.workspace(task).items():
        p = ws / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    cmd = harness_cmd(harness, model, task, ctx, rd, ws, tether_bin, think, can_think, params, steps, fold)
    env = dict(os.environ, OLLAMA_HOST="http://localhost:11435", PYTHONDONTWRITEBYTECODE="1")
    t0 = time.time()
    status = "ok"
    out_f = open(rd / "stdout.txt", "w")
    p = subprocess.Popen(cmd, cwd=ws, env=env, stdout=out_f, stderr=subprocess.STDOUT, text=True,
                         start_new_session=True)
    delivered_steps = None
    while p.poll() is None:
        time.sleep(10)
        # Stop as soon as the work passes its grader: the ladder measures delivery, and a model that
        # keeps polishing (or never calls done) would only burn GPU time. Graded on a copy.
        if time.time() - t0 > 15 and T.grade_copy(task, ws)[0] >= T.pass_threshold(task):
            status = "delivered"
            delivered_steps = steps_now(rd)
            break
        if time.time() - t0 > wall:
            status = "timeout"
            break
    if p.poll() is None:
        os.killpg(p.pid, 15)
        time.sleep(2)
        if p.poll() is None:
            os.killpg(p.pid, 9)
    out_f.close()
    wall_s = time.time() - t0
    score, detail = T.grade(task, ws)
    rec = {"model": model, "task": task.id, "kind": task.kind, "tier": task.tier, "attempt": attempt,
           "think": think and can_think, "params": params, "max_steps": steps, "fold_after": fold, "ctx": ctx,
           "wall_s": round(wall_s), "run_status": status, "delivered_steps": delivered_steps, "score": round(score, 3),
           "pass": score >= T.pass_threshold(task), "detail": detail}
    rec["harness"] = harness
    if harness != "tether":
        rec.update(steps=steps_other(harness, rd), session_status="n/a")
        return rec
    try:
        c = sqlite3.connect(str(rd / "t.db"))
        row = c.execute("select status, step_count, total_prompt_tokens, total_completion_tokens, peak_tokens, result "
                        "from sessions order by created_at desc limit 1").fetchone()
        ev = dict(c.execute("select event_type, count(*) from turns where role='assistant' group by 1").fetchall())
        rec.update(session_status=row[0], steps=row[1], prompt_tokens=row[2], completion_tokens=row[3],
                   peak_tokens=row[4], result=(row[5] or "")[:200], events={k: v for k, v in ev.items() if k not in ("ok", "completed")})
    except Exception as e:  # tether died before creating a session
        rec.update(steps=0, session_status="none", error=repr(e)[:100])
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", default="qwen3.5:9b")
    ap.add_argument("--ctx", default="", help="model=tokens,... context window per model")
    ap.add_argument("--kinds", default=",".join(T.KINDS))
    ap.add_argument("--max-tier", type=int, default=6)
    ap.add_argument("--wall", type=int, default=1200, help="seconds per attempt")
    ap.add_argument("--tether-bin", default="tether")
    ap.add_argument("--harness", default="tether", choices=["tether", "naive", "opencode", "claude"])
    ap.add_argument("--single", action="store_true", help="every task once (attempt 0), no stopping: the harness comparison")
    a = ap.parse_args()
    ctxs = dict(x.split("=") for x in a.ctx.split(",") if x)
    os.makedirs(a.out, exist_ok=True)
    log = Path(a.out) / "results.jsonl"
    done = [json.loads(l) for l in log.open()] if log.exists() else []
    for model in a.models.split(","):
        ctx = int(ctxs.get(model, 8192))
        can_think = a.harness == "tether" and "thinking" in capabilities(model)
        print(f"{model}: context {ctx}, thinking {'yes' if can_think else 'no (attempts 0/1 and 2/3 differ only in steps/temperature)'}", flush=True)
        for kind in a.kinds.split(","):
            for tier in range(1, a.max_tier + 1):
                task = T.TASKS[f"{kind}-{tier}"]
                passed = False
                for attempt in range(1 if a.single else len(ATTEMPTS)):
                    prev = [r for r in done if (r.get("harness", "tether"), r["model"], r["task"], r["attempt"]) == (a.harness, model, task.id, attempt)]
                    rec = prev[0] if prev else None
                    if rec is None:
                        rec = run_attempt(model, task, attempt, ctx, a.out, a.tether_bin, a.wall, can_think, a.harness)
                        done.append(rec)
                        with log.open("a") as fh:
                            fh.write(json.dumps(rec) + "\n")
                    print(f"{a.harness:8} {model:18} {task.id:9} a{attempt} think={int(rec['think'])} score={rec['score']:.2f} "
                          f"{'PASS' if rec['pass'] else 'fail'} {rec['wall_s']}s steps={rec.get('steps')} {rec['detail']}", flush=True)
                    if rec["pass"]:
                        passed = True
                        break
                if not passed and not a.single:
                    print(f"{model:18} {kind}: stopped at tier {tier}", flush=True)
                    break


if __name__ == "__main__":
    main()
