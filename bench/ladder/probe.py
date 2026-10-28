"""Largest context window that keeps a model fully in VRAM: `python3 bench/ladder/probe.py qwen3.5:4b`."""
import sys

import httpx

HOST = "http://localhost:11435"
STEPS = [8192, 16384, 24576, 32768, 40960, 49152, 65536, 81920, 98304, 131072]


def fits(model, ctx):
    httpx.post(f"{HOST}/api/chat", json={"model": model, "messages": [{"role": "user", "content": "hi"}], "stream": False,
               "keep_alive": "30s", "options": {"num_ctx": ctx, "num_predict": 2}}, timeout=600)
    m = [x for x in httpx.get(f"{HOST}/api/ps").json()["models"] if x["name"] == model]
    return bool(m) and m[0]["size"] <= m[0]["size_vram"] * 1.01


def main(model):
    best = 0
    for ctx in STEPS:
        if not fits(model, ctx):
            break
        best = ctx
    print(best)


if __name__ == "__main__":
    main(sys.argv[1])
