# Harness-Bench adapter (pilot, not yet run end to end)

[Harness-Bench](https://github.com/Qihoo360/harness-bench) ([paper](https://arxiv.org/abs/2605.27922)) scores
whole harnesses on 274 offline workflow tasks (plus 26 multimodal) with hidden oracles. This directory holds
the patch that registers Tether as an eighth harness. It is a way to benchmark, not a Tether feature.

`tether-adapter.patch` applies to harness-bench commit `b8d89634c6f445fcc68ceb6744a59bef6cdf4863`:

```bash
git clone https://github.com/Qihoo360/harness-bench && cd harness-bench
git apply /path/to/tether/bench/harness-bench/tether-adapter.patch
uv sync --extra dev
export PYTHONPATH=$PWD/src:$PWD/tools:$PWD/tools/task_maintenance
python tools/run_benchmark.py --base-url "$URL" --model "$MODEL" --harness tether \
    --tasks 001-meeting-summary --workers 1 --run-root /tmp/hb-run
```

What the patch adds: `docker/harnesses/tether/` (their toolchain image plus `tether-sdk`, an entrypoint that runs
`tether run --tools bash,edit` with state kept outside the graded workspace), a `tether` `HarnessSpec`, and a
`providers.yaml` renderer.

Status (2026-10-23): image builds, `tether run` starts inside the trial container and reaches `ProviderError ...
ConnectError`, because on the machine used containers cannot reach host ports (`host.docker.internal`, where the
per-trial model proxy listens). The host firewall must allow the docker bridge to the proxy's ports. No task has
been scored yet.
