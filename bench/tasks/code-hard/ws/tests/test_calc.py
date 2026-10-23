import unittest
from calc import calc, CalcError


class T(unittest.TestCase):
    def test_arith(self):
        self.assertEqual(calc("1+2*3"), 7)

    def test_right_assoc_pow(self):
        self.assertEqual(calc("2^3^2"), 512)

    def test_neg_pow(self):
        self.assertEqual(calc("-2^2"), -4)

    def test_var_digits(self):
        self.assertEqual(calc("x1+1", {"x1": 2}), 3)

    def test_div_zero(self):
        with self.assertRaises(CalcError):
            calc("1/0")


if __name__ == "__main__":
    unittest.main()
