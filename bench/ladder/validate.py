"""Prove the graders: base+files scores < 1 (code), reference scores >= threshold, empty scores 0.

`python3 bench/ladder/validate.py` must print OK for all 24 tasks before a ladder run is trusted.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tasks as T  # noqa: E402
from base import project  # noqa: E402
from refs import REFS  # noqa: E402


def materialize(task, extra=None):
    d = Path(tempfile.mkdtemp(prefix="lad_"))
    for path, text in {**T.workspace(task), **(extra or {})}.items():
        p = d / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return d


def main():
    bad = 0
    for t in T.TASKS.values():
        if t.kind in ("write", "bugfix"):
            before = T.grade(t, materialize(t))[0]
            after = T.grade(t, materialize(t, t.ref))[0]
            ok = before < 0.99 and after >= 0.99
            msg = f"start {before:.2f} -> ref {after:.2f}"
        else:
            empty = T.grade(t, materialize(t))[0]
            ref = T.grade(t, materialize(t, {t.deliverable: REFS[t.id]}))
            ok = empty == 0 and ref[0] >= 0.99
            msg = f"empty {empty:.2f} -> ref {ref[0]:.2f} ({ref[1]})"
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {t.id:10} {msg}")
    # visible tests must pass on the untouched base
    d = Path(tempfile.mkdtemp(prefix="lad_"))
    for path, text in project().items():
        (d / path).parent.mkdir(parents=True, exist_ok=True)
        (d / path).write_text(text)
    import subprocess
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=d, capture_output=True, text=True)
    print("base visible tests:", "OK" if r.returncode == 0 else "BAD\n" + r.stderr[-500:])
    bad += r.returncode != 0
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
