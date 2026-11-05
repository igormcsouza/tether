#!/usr/bin/env bash
# reg_ab.sh: freeze the feat/test-regression-note build, run e2e, then arm D (no params) on the 8 exercises x2.
set -u
WT=/home/walkdead/Projects/tether/.claude/worktrees/describe-failures
OUT=/home/walkdead/Projects/tether/.claude/worktrees/north-star-c852b8/hosted-out
V=/tmp/claude-1000/-home-walkdead-Projects-tether--claude-worktrees-north-star-c852b8/b1bc7023-8e89-46ef-935a-c605f5578993/scratchpad/venv-reg
TASKS=poly-hangman,poly-scale-generator,poly-transpose,poly-connect,poly-rest-api,poly-book-store,poly-variable-length-quantity,poly-go-counting
cd "$WT"
uv venv -q "$V" && uv pip install -q --python "$V/bin/python" . || exit 1
"$V/bin/python" -c "import tether.harness as h; assert hasattr(h, 'regression_note')" || exit 1
echo "== e2e"; TETHER_E2E=1 uv run pytest e2e -q 2>&1 | tail -3
echo "== bench"
uv run python bench/run.py --runners tether --models ollama/qwen3.5:9b --tasks "$TASKS" --trials 2 --poly-verify \
  --tether-bin "$V/bin/tether" --out "$OUT/reg-ab"
