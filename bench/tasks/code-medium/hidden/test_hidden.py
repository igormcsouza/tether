import os, subprocess, sys, tempfile, unittest
from decimal import Decimal
from ledger.parser import parse_rows
from ledger.report import summarize, monthly, render

CSV = open("sample.csv").read().splitlines()


class H(unittest.TestCase):
    def test_summarize(self):
        s = summarize(parse_rows(CSV))
        self.assertEqual(s, [("salary", Decimal("4000.00")), ("rent", Decimal("-800.00")), ("food", Decimal("-42.75"))])

    def test_tie_break(self):
        r = parse_rows(["2024-01-01,b,5,x", "2024-01-01,a,-5,x", "2024-01-01,c,1,x"])
        self.assertEqual([a for a, _ in summarize(r)], ["a", "b", "c"])

    def test_monthly(self):
        m = monthly(parse_rows(CSV))
        self.assertEqual(list(m.items()), [("2024-03", Decimal("1957.25")), ("2024-04", Decimal("1200.00"))])

    def test_render(self):
        f = lambda v: f"{Decimal(v):>10.2f}"
        exp = "\n".join(["salary  " + f("4000"), "rent    " + f("-800"), "food    " + f("-42.75"), "TOTAL   " + f("3157.25")])
        self.assertEqual(render(parse_rows(CSV)), exp)

    def test_render_month(self):
        out = render(parse_rows(CSV), month="2024-04")
        self.assertEqual(out.splitlines()[-1], "TOTAL   " + f"{Decimal('1200'):>10.2f}")
        self.assertNotIn("food", out)

    def test_empty(self):
        self.assertEqual(render([], month="2030-01"), "no data")

    def run_cli(self, *a):
        return subprocess.run([sys.executable, "cli.py", *a], capture_output=True, text=True)

    def test_cli_report(self):
        p = self.run_cli("report", "sample.csv", "--month", "2024-03")
        self.assertEqual(p.returncode, 0)
        self.assertTrue(p.stdout.rstrip("\n").endswith(f"{Decimal('1957.25'):>10.2f}"))

    def test_cli_monthly(self):
        p = self.run_cli("monthly", "sample.csv")
        self.assertEqual(p.stdout.splitlines(), ["2024-03  1957.25", "2024-04  1200.00"])

    def test_cli_errors(self):
        p = self.run_cli("report", "nope.csv")
        self.assertEqual((p.returncode, "cannot read nope.csv" in p.stderr), (2, True))
        p = self.run_cli("report", "sample.csv", "--month", "March")
        self.assertEqual((p.returncode, "bad month" in p.stderr), (2, True))
