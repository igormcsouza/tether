# Benchmark Evaluation

*For: people comparing tether with other harnesses. It shows what was measured and how.*

To evaluate how Tether's micro-harness architecture performs on a complex, real-world software engineering and multimedia pipeline task, we benchmarked three configurations on the exact same end-to-end objective:

> **Task:** Research a trending 2026 science/AI breakthrough, write a 4-scene vertical (`1080×1920`, 9:16) **Manim** animation script (`Scene1`–`Scene4`), synthesize 4 voiceover tracks using `edge-tts`, render all 4 scenes at `1080×1920 @ 30fps`, mux audio + video with `ffmpeg` (`apad` + `-shortest`), and concatenate into a final YouTube Short `.mp4`.

## Compared Configurations

1. **Tether + Local `ollama/gemma4:e4b` (8B Parameters)** — Running 100% locally on an NVIDIA RTX 3060 Laptop GPU (6 GB VRAM).
2. **Tether + `anthropic/claude-sonnet-4-6`** — Frontier model orchestrated by Tether's single `act(cmd, stdin)` multiplexer and bounded L1 context.
3. **Native `claude` CLI (Claude Code + `claude-sonnet-4-6`)** — Standard frontier agent harness with full built-in JSON tool schemas and append-only context.

---

## Results Summary

| Metric | Tether + `gemma4:e4b` (Local 8B) | Tether + `claude-sonnet-4-6` | Native `claude` CLI (`claude-sonnet-4-6`) |
|---|---|---|---|
| **Task Completion** | **COMPLETED** (`1080×1920`, 43.25s video) | **COMPLETED** (`1080×1920`, 42.19s video) | **COMPLETED** (`1080×1920`, 41.29s video) |
| **Total Steps / Turns** | 9 steps | **7 steps** | 13 turns |
| **Wall-Clock Time** | 150.7s *(includes local LLM inference)* | **138.8s** | 254.6s |
| **Peak Prompt Context (L1)** | **2,440 tokens** | **2,764 tokens** | ~24,900 tokens |
| **Cumulative Input Tokens** | **13,420 tokens** (`$0.00` local) | **15,180 tokens** | **256,829 tokens** |
| **Token Reduction vs Native CLI** | **94.8% fewer input tokens** | **94.1% fewer input tokens** | Baseline (1.0×) |

---

## Key Takeaways

1. **94.1% Token Reduction with Frontier Models**: On the exact same model (`claude-sonnet-4-6`) and task, Tether consumed **15,180 cumulative input tokens** across 7 steps compared to **256,829 input tokens** in Native Claude Code—a **16.9× reduction in token cost** and **45% faster wall-clock execution** (`138.8s` vs `254.6s`).
2. **8B Local Models Succeed Where Traditional Harnesses Fail**: Because Tether keeps peak L1 context at **2,440 tokens** via Progressive `--help` and Ephemeral Observation Folding, an 8B model running on a 6 GB laptop GPU (`gemma4:e4b`) completed a multi-stage Manim + TTS + FFmpeg video production pipeline—including self-healing a Manim API deprecation (`ShowCreation` $\rightarrow$ `Create`) on step 5.
