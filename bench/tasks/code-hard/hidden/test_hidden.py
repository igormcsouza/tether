import unittest
from calc import calc, CalcError


class H(unittest.TestCase):
    def test_basic(self):
        for s, e in [("1+2*3", 7), ("(1+2)*3", 9), ("10/4", 2.5), ("2*3-4", 2), ("1 - 2 - 3", -4), ("8/2/2", 2),
                     ("1.5e3+1", 1501), (".5+.5", 1), ("  7  ", 7)]:
            self.assertAlmostEqual(calc(s), e, msg=s)

    def test_pow(self):
        for s, e in [("2^3^2", 512), ("2^10", 1024), ("(2^3)^2", 64), ("2^-1", 0.5), ("2*3^2", 18), ("4^0.5", 2)]:
            self.assertAlmostEqual(calc(s), e, msg=s)

    def test_unary(self):
        for s, e in [("-2^2", -4), ("-2*3", -6), ("--3", 3), ("-(1+2)", -3), ("2*-3", -6), ("-2^2^2", -16), ("1--1", 2), ("+5", 5)]:
            self.assertAlmostEqual(calc(s), e, msg=s)

    def test_vars(self):
        env = {"x1": 3, "my_var": 4, "y": 2, "a2b": 1}
        for s, e in [("x1+1", 4), ("my_var*y", 8), ("a2b+x1", 4), ("x1^y", 9), ("-x1", -3)]:
            self.assertAlmostEqual(calc(s, env), e, msg=s)

    def test_funcs(self):
        for s, e in [("min(3,1,2)", 1), ("max(1, 2^3)", 8), ("abs(-4)", 4), ("sqrt(16)", 4), ("max(abs(-2), min(5,6))", 5)]:
            self.assertAlmostEqual(calc(s), e, msg=s)

    def test_errors(self):
        for s in ["1/0", "2/(1-1)", "x", "foo(1)", "abs(1,2)", "sqrt(-1)", "1 +", "(1", "1 $ 2", "min()", "1 2"]:
            with self.assertRaises(CalcError, msg=s):
                calc(s)
