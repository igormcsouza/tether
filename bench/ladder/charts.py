"""Draw the ladder charts as plain SVG (no dependencies): `python3 bench/ladder/charts.py` -> docs/ladder/img/.

Colours are mid-tones with a transparent background, so the same file reads on the light and dark
themes of the docs site.
"""
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "docs", "ladder", "img")
MODELS = ["qwen3.5:9b", "qwen3.5:4b", "qwen2.5-coder:7b"]
COLORS = {"qwen3.5:9b": "#2a9d8f", "qwen3.5:4b": "#e9a23b", "qwen2.5-coder:7b": "#7b6fd0"}
HCOLORS = {"tether": "#2a9d8f", "naive": "#8a8f98", "opencode": "#d9694e"}
KINDS = ["write", "bugfix", "plan", "review"]
TXT = "#8a8f98"
FONT = "font-family='system-ui,sans-serif'"


def load(name):
    return [json.loads(l) for l in open(os.path.join(HERE, "baseline", name))]


def svg(w, h, body):
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {w} {h}' width='{w}' height='{h}' {FONT}>"
            f"{body}</svg>")


def text(x, y, s, size=12, anchor="start", weight="normal", fill=TXT):
    return f"<text x='{x}' y='{y}' font-size='{size}' text-anchor='{anchor}' font-weight='{weight}' fill='{fill}'>{s}</text>"


def legend(items, x, y):
    out = ""
    for i, (label, color) in enumerate(items):
        out += f"<rect x='{x + i * 150}' y='{y - 10}' width='12' height='12' rx='2' fill='{color}'/>"
        out += text(x + i * 150 + 18, y, label)
    return out


def tiers_chart(rows):
    """Highest tier passed, per kind and model (ladder runs)."""
    best = defaultdict(int)
    for r in rows:
        if r["pass"]:
            best[(r["model"], r["kind"])] = max(best[(r["model"], r["kind"])], r["tier"])
    w, h, left, top, bottom = 640, 330, 50, 40, 40
    ph = h - top - bottom
    body = legend([(m, COLORS[m]) for m in MODELS], left, 18)
    for t in range(7):
        y = top + ph - ph * t / 6
        body += f"<line x1='{left}' x2='{w - 10}' y1='{y}' y2='{y}' stroke='{TXT}' stroke-opacity='.25'/>"
        body += text(left - 8, y + 4, t, anchor="end")
    gw = (w - left - 20) / len(KINDS)
    for i, kind in enumerate(KINDS):
        for j, m in enumerate(MODELS):
            v = best[(m, kind)]
            bw = gw / (len(MODELS) + 1)
            x = left + i * gw + (j + 0.5) * bw
            bh = ph * v / 6
            body += f"<rect x='{x:.1f}' y='{top + ph - bh:.1f}' width='{bw - 4:.1f}' height='{bh:.1f}' rx='3' fill='{COLORS[m]}'/>"
            body += text(x + (bw - 4) / 2, top + ph - bh - 4, v, 11, "middle")
        body += text(left + i * gw + gw / 2, h - 14, kind, 13, "middle", "600")
    body += text(left, h - 1, "highest tier passed (0 = not even tier 1), up to 4 attempts per tier", 11)
    return svg(w, h, body)


def label_rows(rows):
    by = defaultdict(dict)
    for r in rows:
        by[(r["model"], r["label"])][r["task"]] = r
    return by


def harness_chart(rows):
    """Passed tasks of 24, per model and harness."""
    by = label_rows(rows)
    labels = ["tether", "naive", "opencode"]
    w, h, left, top, bottom = 640, 330, 50, 40, 40
    ph = h - top - bottom
    body = legend([("tether", HCOLORS["tether"]), ("bare tool loop", HCOLORS["naive"]), ("opencode", HCOLORS["opencode"])], left, 18)
    for t in range(0, 25, 6):
        y = top + ph - ph * t / 24
        body += f"<line x1='{left}' x2='{w - 10}' y1='{y}' y2='{y}' stroke='{TXT}' stroke-opacity='.25'/>"
        body += text(left - 8, y + 4, t, anchor="end")
    gw = (w - left - 20) / len(MODELS)
    for i, m in enumerate(MODELS):
        for j, lab in enumerate(labels):
            runs = [v for (mm, l), v in by.items() if mm == m and l.split("-")[0] == lab]
            if not runs:
                continue
            counts = [sum(r["pass"] for r in v.values()) for v in runs]
            bw = gw / 4
            x = left + i * gw + (j + 0.5) * bw
            for k, c in enumerate(counts):  # several tether runs of one model: bars side by side
                bh = ph * c / 24
                sub = (bw - 4) / len(counts)
                body += f"<rect x='{x + k * sub:.1f}' y='{top + ph - bh:.1f}' width='{sub - 2:.1f}' height='{bh:.1f}' rx='3' fill='{HCOLORS[lab]}'/>"
                body += text(x + k * sub + (sub - 2) / 2, top + ph - bh - 4, c, 11, "middle")
        body += text(left + i * gw + gw / 2, h - 14, m, 13, "middle", "600")
    body += text(left, h - 1, "tasks passed of 24, every task once with the first-attempt settings", 11)
    return svg(w, h, body)


def cost_chart(rows):
    """Wall minutes and mean steps per task, 9b and each harness."""
    by = label_rows(rows)
    items = []
    for (m, lab), v in sorted(by.items()):
        if m == "qwen3.5:9b" and len(v) == 24:
            steps = [r.get("delivered_steps") or r.get("steps") or 0 for r in v.values()]
            items.append((lab, sum(r["wall_s"] for r in v.values()) / 60, sum(steps) / len(steps)))
    w, h = 640, 40 + 52 * len(items) + 30
    body = text(150, 22, "wall time, minutes (24 tasks)", 12, fill=TXT) + text(420, 22, "mean steps per task", 12, fill=TXT)
    mx_t, mx_s = max(i[1] for i in items), max(i[2] for i in items)
    for k, (lab, mins, steps) in enumerate(items):
        y = 40 + 52 * k
        color = HCOLORS[lab.split("-")[0]]
        body += text(140, y + 22, lab, 12, "end")
        body += f"<rect x='150' y='{y + 6}' width='{230 * mins / mx_t:.0f}' height='24' rx='3' fill='{color}'/>"
        body += text(150 + 230 * mins / mx_t + 6, y + 23, f"{mins:.0f}", 12)
        body += f"<rect x='420' y='{y + 6}' width='{170 * steps / mx_s:.0f}' height='24' rx='3' fill='{color}'/>"
        body += text(420 + 170 * steps / mx_s + 6, y + 23, f"{steps:.1f}", 12)
    return svg(w, h, body)


def grid_chart(rows):
    """Pass/fail of the 24 tasks, tether, every model: where the wall is."""
    by = label_rows(rows)
    tasks = [f"{k}-{t}" for k in KINDS for t in range(1, 7)]
    cell, left, top = 38, 130, 52
    w, h = left + cell * 6 + 20, top + (len(MODELS) * 4 + 4) * 0 + 4 * (cell + 8) * len(MODELS) // 1 // 1
    h = top + len(MODELS) * (len(KINDS) * (cell - 12) + 18) + 10
    body = ""
    for t in range(6):
        body += text(left + t * cell + cell / 2 - 2, 40, f"T{t + 1}", 12, "middle", "600")
    y = top
    for m in MODELS:
        runs = [v for (mm, l), v in by.items() if mm == m and l.split("-")[0] == "tether"]
        if not runs:
            continue
        run = runs[0]
        body += text(8, y + 12, m, 13, weight="600")
        y += 18
        for kind in KINDS:
            body += text(left - 10, y + 18, kind, 12, "end")
            for t in range(1, 7):
                r = run.get(f"{kind}-{t}")
                fill = "#2a9d8f" if r and r["pass"] else "#d9694e" if r else TXT
                op = 1 if r else 0.2
                s = f"{r['score']:.1f}" if r else ""
                body += f"<rect x='{left + (t - 1) * cell}' y='{y}' width='{cell - 4}' height='{cell - 16}' rx='3' fill='{fill}' fill-opacity='{op}'/>"
                body += text(left + (t - 1) * cell + (cell - 4) / 2, y + 17, s, 11, "middle", fill="#fff")
            y += cell - 12
        y += 6
    return svg(w, y + 10, body)


def main():
    os.makedirs(OUT, exist_ok=True)
    ladder, harness = load("ladder.jsonl"), load("harness.jsonl")
    for name, fn, data in (("tiers", tiers_chart, ladder), ("harness-pass", harness_chart, harness),
                           ("harness-cost", cost_chart, harness), ("task-grid", grid_chart, harness)):
        open(os.path.join(OUT, f"{name}.svg"), "w").write(fn(data))
        print("wrote", name)


if __name__ == "__main__":
    main()
