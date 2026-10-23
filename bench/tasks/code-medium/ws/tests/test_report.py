import unittest
from decimal import Decimal
from ledger.parser import parse_rows
from ledger.report import summarize

ROWS = ["2024-03-01,food,-12.50,x", "2024-03-02,salary,2000,y"]


class T(unittest.TestCase):
    def test_summarize(self):
        self.assertEqual(summarize(parse_rows(ROWS))[0], ("salary", Decimal("2000")))


if __name__ == "__main__":
    unittest.main()
