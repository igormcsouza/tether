"""Shopping cart."""
from shop.pricing import bulk_price


class Cart:
    def __init__(self, inventory):
        self.inventory = inventory
        self.lines = {}
        self.coupon_code = None

    def add(self, sku, qty=1):
        self.inventory.get(sku)
        self.lines[sku] = self.lines.get(sku, 0) + qty

    def apply_coupon(self, code):
        if code == "SAVE10":
            self.coupon_discount = 0.10
        elif code == "FIVEOFF":
            self.coupon_discount = 5.0
        else:
            raise ValueError("Unknown coupon code")

    def total(self):
        subtotal = sum(bulk_price(self.inventory.get(s)["price"], q) for s, q in self.lines.items())
        discount = self.coupon_discount * subtotal if isinstance(self.coupon_discount, float) else self.coupon_discount
        return round(max(0, subtotal - discount), 2)
