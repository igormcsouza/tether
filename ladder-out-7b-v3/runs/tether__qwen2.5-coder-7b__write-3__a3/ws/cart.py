class Cart:
    def __init__(self):
        self.items = []
        self.coupon = None

    def add_item(self, item, price):
        self.items.append((item, price))

    def total(self):
        total = sum(price for _, price in self.items)
        if self.coupon == 'SAVE10':
            total -= total * 0.10
        elif self.coupon == 'FIVEOFF':
            total = max(total - 5, 0)
        return total

    def apply_coupon(self, code):
        if code == 'SAVE10' or code == 'FIVEOFF':
            self.coupon = code
        else:
            raise ValueError('Unknown coupon code')