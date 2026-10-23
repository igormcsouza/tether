import math

from .errors import CalcError

FUNCS = {"min": (1, None, min), "max": (1, None, max), "abs": (1, 1, abs), "sqrt": (1, 1, math.sqrt)}


def evaluate(node, env):
    k = node[0]
    if k == "num":
        return node[1]
    if k == "var":
        if node[1] not in env:
            raise CalcError(f"undefined variable {node[1]}")
        return env[node[1]]
    if k == "neg":
        return -evaluate(node[1], env)
    if k == "bin":
        op = node[1]
        a, b = evaluate(node[2], env), evaluate(node[3], env)
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return a / b
        if op == "^":
            return a**b
    if k == "call":
        name, args = node[1], node[2]
        if name not in FUNCS:
            raise CalcError(f"unknown function {name}")
        lo, hi, fn = FUNCS[name]
        if len(args) < lo or (hi is not None and len(args) > hi):
            raise CalcError(f"{name}: wrong number of arguments")
        vals = [evaluate(a, env) for a in args]
        if name == "sqrt" and vals[0] < 0:
            raise CalcError("sqrt of negative number")
        return fn(*vals)
    raise CalcError("bad node")
