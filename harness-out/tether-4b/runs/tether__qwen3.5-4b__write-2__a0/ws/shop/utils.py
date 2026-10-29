"""Small helpers."""


def clamp(value, low, high):
    return max(low, min(high, value))


def money(amount):
    return f"${amount:,.2f}"


def slugify(text):
    # Lowercase the text
    text = text.lower()
    # Replace every run of non-alphanumeric characters with a single '-'
    import re
    text = re.sub(r'[^a-z0-9]+', '-', text)
    # Strip leading and trailing '-'
    return text.strip('-')