"""Shopping cart."""
from shop.pricing import bulk_price


class Cart:
    def __init__(self, inventory):
        self.inventory = inventory
        self.lines = {}
        self.coupon = None

    def add(self, sku, qty=1):
        self.inventory.get(sku)
        self.lines[sku] = self.lines.get(sku, 0) + qty

    def apply_coupon(self, code):
        """Apply a coupon code to the cart."""
        if code == "SAVE10":
            self.coupon = "SAVE10"
        elif code == "FIVEOFF":
            self.coupon = "FIVEOFF"
        else:
            raise ValueError(f"Unknown coupon code: {code}")

    def total(self):
        subtotal = round(
            sum(bulk_price(self.inventory.get(s)["price"], q) for s, q in self.lines.items()), 2
        )
        
        if self.coupon == "SAVE10":
            return round(subtotal * 0.9, 2)
        elif self.coupon == "FIVEOFF":
            return max(0, round(subtotal - 5, 2))
        else:
            return subtotal