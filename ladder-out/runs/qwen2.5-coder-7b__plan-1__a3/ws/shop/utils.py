"""Small helpers."""


def clamp(value, low, high):
    return max(low, min(high, value))


def money(amount):
    return f"${amount:,.2f}"
