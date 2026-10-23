import re


def slugify(text):
    """Lowercase, replace runs of non-alphanumerics with a single '-', no leading/trailing '-'."""
    return re.sub(r"[^a-z0-9]", "-", text.lower())


def truncate_words(text, n):
    """Return the first n words; append '…' only if words were dropped."""
    words = text.split()
    if len(words) <= n:
        return text
    return " ".join(words[: n + 1]) + "…"
