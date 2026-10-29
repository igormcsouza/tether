"""Price calculations."""

BULK_THRESHOLD = 10


def line_total(unit_price, quantity):
    return round(unit_price * quantity, 2)


def bulk_price(unit_price, quantity):
    """10% off every unit once the quantity reaches the bulk threshold."""
    if quantity >= BULK_THRESHOLD:
        return round(unit_price * quantity * 0.9, 2)
    return line_total(unit_price, quantity)


def apply_discount(price, pct):
    return round(price * (1 - pct / 100), 2)
