import re

from .errors import CalcError

TOKEN = re.compile(r"\s*(?:(\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+)|([A-Za-z_][A-Za-z0-9_]*)|(.))")


def tokenize(src):
    toks, pos, src = [], 0, src.rstrip()
    while pos < len(src):
        m = TOKEN.match(src, pos)
        if not m:
            break
        num, ident, op = m.groups()
        pos = m.end()
        if num:
            toks.append(("num", float(num)))
        elif ident:
            toks.append(("id", ident))
        else:
            if op not in "+-*/^(),":
                raise CalcError(f"unexpected character {op!r}")
            toks.append(("op", op))
    return toks
