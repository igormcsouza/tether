import unittest

from shop.pricing import bulk_price, line_total


class PricingTest(unittest.TestCase):
    def test_line_total(self):
        self.assertEqual(line_total(2.5, 4), 10.0)

    def test_bulk_starts_at_ten(self):
        self.assertEqual(bulk_price(10, 10), 90.0)
        self.assertEqual(bulk_price(10, 9), 90.0)
        self.assertEqual(bulk_price(10, 2), 20.0)
