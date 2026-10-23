from .errors import CalcError
from .evaluator import evaluate
from .parser import Parser
from .tokenizer import tokenize


def calc(src, env=None):
    """Evaluate an arithmetic expression: + - * / ^ (right assoc), unary minus, parens,
    variables from env, functions min/max/abs/sqrt. Raises CalcError on any user error."""
    return evaluate(Parser(tokenize(src)).parse(), env or {})
