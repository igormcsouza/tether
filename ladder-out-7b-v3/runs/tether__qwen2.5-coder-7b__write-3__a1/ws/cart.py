class Cart:
    def __init__(self, items, total):
        self.items = items
        self.total = total

    def apply_coupon(self, code):
        if code == 'SAVE10':
            self.total *= 0.9
        elif code == 'FIVEOFF':
            self.total = max(self.total - 5, 0)
        else:
            raise ValueError('Unknown coupon code')

    def total(self):
        return self.total