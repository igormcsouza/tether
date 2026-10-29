"""Small helpers."""


def clamp(value, low, high):
    return max(low, min(high, value))


def money(amount):
    return f"${amount:,.2f}"


def slugify(text):
    import re
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = text.strip('-')
    return text
