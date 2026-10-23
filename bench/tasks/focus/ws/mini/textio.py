"""File reading helpers."""


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()
