import unittest

from shop.report import monthly, summary

ORDERS = [
    {"id": 1, "date": "2025-01-05", "region": "US-CA", "total": 10.5},
    {"id": 2, "date": "2025-01-20", "region": "EU", "total": 4.25},
    {"id": 3, "date": "2025-02-02", "region": "US-NY", "total": 7.0},
]


class ReportTest(unittest.TestCase):
    def test_summary(self):
        self.assertEqual(summary(ORDERS), {"count": 3, "revenue": 21.75})

    def test_monthly(self):
        self.assertEqual(monthly(ORDERS), {"2025-01": 14.75, "2025-02": 7.0})
