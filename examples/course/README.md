# Course-builder example

A three-stage tether pipeline that builds a small Portuguese course with a local model. It is the running example in the docs; each feature page borrows a snippet from here.

| Stage | Skill | Tools | Gate |
|---|---|---|---|
| `plan` | `planner` | `edit` | `python3 checks.py plan` (1 to 3 modules, each with topics) |
| `videos` | `searcher` | `yt-todo`, `yt-candidates`, `yt-save` | `python3 checks.py videos` (every topic has a video) |
| `course` | `writer` | `edit`, `course-source`, `course-build` | `python3 checks.py course` (no invented links, none missing) |

## Run

```sh
ollama pull qwen3.5:9b   # or point OLLAMA_HOST at a container, see the CLI page of the docs
cd examples/course
tether pipeline course.yaml "Mini-curso de Arquitetura de Software"
```

Outputs `plan.md`, `videos.md`, `part-N.md` and `course.md` in the current directory. `yt-candidates` scrapes YouTube, so it needs network access from the host (the tools run in your process, not in the `bash` sandbox).

If a stage runs out of `max_steps`, progress is in the files; finish by hand, for example `tether run --skill searcher "Escolha 1 vídeo para cada tópico de plan.md"`.
