"""YouTube tools: the model picks a numbered candidate for a plan topic; code copies the URL exactly."""

import json
import re
import unicodedata
import urllib.parse
import urllib.request

from tether import tool

CHANNEL = "https://www.youtube.com/@RenatoAugustoTech/videos?view=0&sort=p"
STATE = ".yt_cands.json"


def _page(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "pt-BR"}
    )
    html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    return json.loads(m.group(1)) if m else {}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _words(s: str) -> set:
    return {w for w in re.findall(r"\w+", _norm(s)) if len(w) > 3}


def _walk(node, out, channel_name):
    if isinstance(node, dict):
        if node.get("contentType") == "LOCKUP_CONTENT_TYPE_VIDEO":  # channel grid
            meta = node["metadata"]["lockupMetadataViewModel"]
            v = re.search(
                r'"accessibilityLabel": "([^"]*visualiza[^"]*)"',
                json.dumps(meta, ensure_ascii=False),
            )
            out.append(
                {
                    "id": node["contentId"],
                    "title": meta["title"]["content"],
                    "channel": channel_name,
                    "views": v.group(1).replace(" visualizações", "") if v else "",
                }
            )
        elif "videoRenderer" in node:  # search results
            r = node["videoRenderer"]
            owner = "".join(x["text"] for x in r.get("ownerText", {}).get("runs", []))
            out.append(
                {
                    "id": r["videoId"],
                    "title": "".join(x["text"] for x in r["title"]["runs"]),
                    "channel": owner,
                    "views": r.get("viewCountText", {})
                    .get("simpleText", "")
                    .replace(" visualizações", ""),
                }
            )
        for x in node.values():
            _walk(x, out, channel_name)
    elif isinstance(node, list):
        for x in node:
            _walk(x, out, channel_name)


def _read(path: str) -> str:
    try:
        return open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return ""


def _topics() -> dict:
    """ref ('1.2') -> topic text, parsed from plan.md (module = '## Módulo', topic = '- ')."""
    out, m, t = {}, 0, 0
    for line in _read("plan.md").splitlines():
        if line.startswith("## Módulo"):
            m, t = m + 1, 0
        elif line.startswith("- ") and m:
            t += 1
            out[f"{m}.{t}"] = line[2:].strip()
    return out


def _query(topic: str) -> str:
    """Search words from a topic line: drop markdown and any ': description' tail."""
    return re.split(r"\s[:\-–—]\s|:", re.sub(r"[*_`]", "", topic))[0].strip()


def _saved_refs() -> set:
    return {r.split(" | ")[0] for r in _read("videos.md").splitlines() if " | " in r}


@tool(name="yt-todo", description="List plan topics that still need a video")
def yt_todo() -> str:
    """Pending topic refs (module.topic) from plan.md with their text."""
    done = _saved_refs()
    left = [f"{r} {t}" for r, t in _topics().items() if r not in done]
    return "\n".join(left) if left else "ALL DONE: every topic has a video. Call done."


@tool(name="yt-candidates", description="Numbered YouTube candidates for a topic ref like 1.2")
def yt_candidates(ref: str) -> str:
    """Up to 5 numbered videos for plan topic REF (e.g. 1.2); extra words after the ref refine the search."""
    key, _, extra = ref.strip().partition(" ")
    topics = _topics()
    if key not in topics:
        return (
            "unknown ref; use one from yt-todo: " + ", ".join(topics)
            if topics
            else "plan.md has no topics"
        )
    subject = next(
        (
            re.sub(r"(?i)\b(mini-?)?curso( de| sobre)?\b|[:#]", "", line).strip()
            for line in _read("plan.md").splitlines()
            if line.startswith("# ")
        ),
        "",
    )
    query = " ".join(x for x in (_query(topics[key]), subject, extra) if x)
    have, words = (
        _read("videos.md"),
        _words(_query(topics[key]) + " " + extra),
    )  # topic words only: the course subject must not match every channel video
    chan: list = []
    _walk(_page(CHANNEL), chan, "Renato Augusto")
    chan = sorted(
        (c for c in chan if words & _words(c["title"])),
        key=lambda c: -len(words & _words(c["title"])),
    )[:2]
    found: list = []
    _walk(
        _page(
            "https://www.youtube.com/results?search_query="
            + urllib.parse.quote(query + " português")
        ),
        found,
        "",
    )
    cands: list = []
    for c in chan + found:
        if c["id"] not in have and all(c["id"] != x["id"] for x in cands):
            cands.append(c)
    cands = cands[:5]
    if not cands:
        return "no new results; add different words after the ref"
    json.dump(
        {"ref": key, "topic": topics[key], "cands": cands}, open(STATE, "w"), ensure_ascii=False
    )
    lines = [f"{i}. {c['title']} | {c['channel']} | {c['views']}" for i, c in enumerate(cands, 1)]
    return (
        f"topic {key}: {topics[key]}\n"
        + "\n".join(lines)
        + "\nPick the best one for this topic (Portuguese, a real lesson): yt-save <number>"
    )


@tool(name="yt-save", description="Save candidate N for the topic of the last yt-candidates")
def yt_save(number: int) -> str:
    """Save candidate NUMBER for the topic last listed by yt-candidates (code copies the exact URL)."""
    try:
        st = json.load(open(STATE))
        c = st["cands"][number - 1]
    except (FileNotFoundError, IndexError, KeyError):
        return "no such candidate; run yt-candidates <ref> first"
    if st["ref"] in _saved_refs():
        return f"topic {st['ref']} already has a video"

    def clean(x):
        return (
            x.replace(" | ", " – ").replace("|", "–").replace("\n", " ")
        )  # '|' is the videos.md column separator

    open("videos.md", "a").write(
        f"{st['ref']} | {clean(st['topic'])} | {clean(c['title'])} | https://www.youtube.com/watch?v={c['id']} | {clean(c['channel'])} | {c['views']}\n"
    )
    return f"saved {st['ref']}: {c['title']}"
