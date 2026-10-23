from .errors import CalcError

PREC = {"+": 1, "-": 1, "*": 2, "/": 2, "^": 4}
RIGHT = set()
NEG_PREC = 5


class Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self):
        e = self.expr(1)
        if self.peek() is not None:
            raise CalcError(f"unexpected token {self.peek()[1]!r}")
        return e

    def expr(self, minp):
        left = self.unary()
        while True:
            tok = self.peek()
            if not tok or tok[0] != "op" or tok[1] not in PREC:
                break
            op = tok[1]
            p = PREC[op]
            if p < minp:
                break
            self.next()
            right = self.expr(p if op in RIGHT else p + 1)
            left = ("bin", op, left, right)
        return left

    def unary(self):
        tok = self.peek()
        if tok == ("op", "-"):
            self.next()
            return ("neg", self.expr(NEG_PREC))
        if tok == ("op", "+"):
            self.next()
            return self.unary()
        return self.atom()

    def atom(self):
        tok = self.next()
        if tok is None:
            raise CalcError("unexpected end of input")
        k, v = tok
        if k == "num":
            return ("num", v)
        if k == "id":
            if self.peek() == ("op", "("):
                self.next()
                args = []
                if self.peek() != ("op", ")"):
                    while True:
                        args.append(self.expr(1))
                        if self.peek() == ("op", ","):
                            self.next()
                            continue
                        break
                if self.next() != ("op", ")"):
                    raise CalcError("expected ')'")
                return ("call", v, args)
            return ("var", v)
        if v == "(":
            e = self.expr(1)
            if self.next() != ("op", ")"):
                raise CalcError("expected ')'")
            return e
        raise CalcError(f"unexpected token {v!r}")
