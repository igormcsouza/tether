"""Deterministic graders. grade(task, ws, result_text) -> {"score": 0..1, "pass": bool, "detail": {...}}"""
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = os.path.join(HERE, "tasks")


def _tree_hash(path):
    h = hashlib.sha256()
    for root, _, files in sorted(os.walk(path)):
        for f in sorted(files):
            if f.endswith(".pyc"):
                continue
            p = os.path.join(root, f)
            h.update(os.path.relpath(p, path).encode())
            h.update(open(p, "rb").read())
    return h.hexdigest()


def _code(task, ws, _result):
    tmp = tempfile.mkdtemp(prefix="g_")
    try:
        shutil.copytree(ws, tmp, dirs_exist_ok=True)
        orig_tests = os.path.join(TASKS, task, "ws", "tests")
        tampered = os.path.isdir(orig_tests) and _tree_hash(orig_tests) != _tree_hash(os.path.join(ws, "tests"))
        shutil.copy(os.path.join(TASKS, task, "hidden", "test_hidden.py"), os.path.join(tmp, "_hidden_test.py"))
        try:
            p = subprocess.run([sys.executable, "-m", "unittest", "-v", "_hidden_test"], cwd=tmp, capture_output=True,
                               text=True, timeout=90)
            out = p.stderr + p.stdout
        except subprocess.TimeoutExpired:
            return {"score": 0.0, "pass": False, "detail": {"error": "hidden tests timed out"}}
        ok = len(re.findall(r"\.\.\. ok$", out, re.M))
        bad = len(re.findall(r"\.\.\. (FAIL|ERROR)$", out, re.M))
        total = ok + bad
        score = ok / total if total else 0.0
        if tampered:
            return {"score": 0.0, "pass": False, "detail": {"tampered_tests": True, "hidden_ok": ok, "hidden_total": total}}
        return {"score": round(score, 3), "pass": total > 0 and bad == 0, "detail": {"hidden_ok": ok, "hidden_total": total}}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _json_array(text):
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return None
    for parse in (json.loads, ast.literal_eval):
        try:
            v = parse(m.group(0))
            return v if isinstance(v, list) else None
        except (ValueError, SyntaxError):
            pass
    return None


def _qa(_task, _ws, result):
    arr = _json_array(result)
    checks = [
        lambda a: "17:25" in a,
        lambda a: re.search(r"\b391(\.0+)?\b", a) is not None,
        lambda a: "canberra" in a.lower(),
        lambda a: re.sub(r"\s", "", a) == "[1,3]",
        lambda a: re.search(r"\b(10|ten)\b", a.lower()) is not None,
        lambda a: ("1024" in a or "2**10" in a.replace(" ", "") or "2^10" in a.replace(" ", "")) and re.search(r"\b24\b", a) is not None,
    ]
    if arr is None or len(arr) != 6:
        return {"score": 0.0, "pass": False, "detail": {"error": "not a JSON array of 6"}}
    got = [bool(c(str(a))) for c, a in zip(checks, arr)]
    return {"score": round(sum(got) / 6, 3), "pass": all(got), "detail": {"correct": got}}


def _content(_task, _ws, result):
    t = (result or "").strip()
    words = len(re.findall(r"\S+", t))
    lines = [ln for ln in t.splitlines() if ln.strip()]
    sentences = re.split(r"(?<=[.?])\s+", t.replace("\n", " "))
    last = sentences[-1] if sentences else ""
    c = {
        "<=120 words": words <= 120 and words > 0,
        "3 bullets": sum(1 for ln in lines if ln.startswith("- ")) == 3,
        "snapshot": "snapshot" in t.lower(),
        "rollback": "rollback" in t.lower(),
        "CTA last": "tidepool.dev" in last.lower(),
        "no !": "!" not in t,
        "no banned": not re.search(r"revolutionary|game-changing", t, re.I),
    }
    return {"score": round(sum(c.values()) / len(c), 3), "pass": all(c.values()), "detail": {"checks": c, "words": words}}


FLAWS = {
    "selection/no-randomisation": r"random|self-select|selection bias|volunteer|chose to install|non-?random|assign",
    "causal-overreach": r"causal|causation|\bcause|correlat|overreach|overstat",
    "tiny-sample/generalise": r"small sample|sample size|n\s*=\s*1[12]|23 (student|participant)|under-?power|low power|generali[sz]|single (university|course)|one (course|university)",
    "multiple-comparisons": r"multiple (comparison|testing|outcome|test)|bonferroni|family-?wise|false[- ]positive|correction|cherry|selective",
    "number-inconsistency": r"inconsisten|discrepan|mismatch|contradict|12\.4.{0,80}(8\.1|7\.2)|(8\.1|7\.2).{0,80}12\.4",
    "baseline-gpa-imbalance": r"gpa|baseline|prior (performance|achievement|ability)|confound|not matched|unmatched|equivalen",
    "unblinded-grader": r"blind|grader|grading|instructor|assessor|rater",
    "no-effect-size/CI": r"effect size|confidence interval|\bCIs?\b|cohen",
}


def _review(_task, _ws, result):
    t = result or ""
    hit = {k: bool(re.search(v, t, re.I)) for k, v in FLAWS.items()}
    n = len(re.findall(r"^\s*\d+[.)]", t, re.M))
    return {"score": round(sum(hit.values()) / len(hit), 3), "pass": sum(hit.values()) >= 6,
            "detail": {"found": [k for k, v in hit.items() if v], "missed": [k for k, v in hit.items() if not v], "items": n}}


def grade(task, ws, result):
    fn = {"qa": _qa, "content": _content, "review": _review}.get(task, _code)
    try:
        return fn(task, ws, result)
    except Exception as e:  # grader bug must never look like a model result
        return {"score": 0.0, "pass": False, "detail": {"grader_error": repr(e)}}


if __name__ == "__main__":
    task, ws, rf = sys.argv[1:4]
    print(json.dumps(grade(task, ws, open(rf).read() if os.path.exists(rf) else "")))
