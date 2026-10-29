class Cart:
    def __init__(self):
        self.items = []
        self.coupon = None

    def add_item(self, price):
        self.items.append(price)

    def apply_coupon(self, code):
        if code == 'SAVE10':
            self.coupon = lambda total: max(total * 0.9, 0)
        elif code == 'FIVEOFF':
            self.coupon = lambda total: max(total - 5, 0)
        else:
            raise ValueError('Unknown coupon code')

    def total(self):
        total = sum(self.items)
        if self.coupon:
            total = self.coupon(total)
        return total