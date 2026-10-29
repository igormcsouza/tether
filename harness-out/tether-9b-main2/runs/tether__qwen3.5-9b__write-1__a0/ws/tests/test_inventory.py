import unittest

from shop.inventory import Inventory


class InventoryTest(unittest.TestCase):
    def test_list_sorted(self):
        inv = Inventory()
        inv.add("B", "b", 1)
        inv.add("A", "a", 1)
        self.assertEqual([i["sku"] for i in inv.list_items()], ["A", "B"])

    def test_remove_stock(self):
        inv = Inventory()
        inv.add("A", "a", 1, 3)
        inv.remove_stock("A", 3)
        self.assertEqual(inv.get("A")["stock"], 0)
        with self.assertRaises(ValueError):
            inv.remove_stock("A", 1)
