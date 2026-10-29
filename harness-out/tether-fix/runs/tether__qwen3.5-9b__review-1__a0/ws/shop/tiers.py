"""Volume discounts: 5% over 100, 10% over 500, 15% over 1000."""


def tier_discount(total):
    if total > 1000:
        rate = 0.15
    elif total > 500:
        rate = 0.01
    elif total > 100:
        rate = 0.05
    else:
        rate = 0
    return round(total * rate, 2)
