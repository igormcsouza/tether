import unittest

from shop.cart import Cart
from shop.inventory import Inventory


class CartTest(unittest.TestCase):
    def setUp(self):
        self.inv = Inventory()
        self.inv.add("A1", "pen", 2.0, 100)
        self.inv.add("B2", "book", 12.5, 5)

    def test_total(self):
        cart = Cart(self.inv)
        cart.add("A1", 3)
        cart.add("B2")
        self.assertEqual(cart.total(), 18.5)

    def test_same_sku_adds_up(self):
        cart = Cart(self.inv)
        cart.add("A1", 2)
        cart.add("A1", 3)
        self.assertEqual(cart.lines["A1"], 5)
