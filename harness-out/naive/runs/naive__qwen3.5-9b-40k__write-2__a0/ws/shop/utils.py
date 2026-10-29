"""Small helpers."""


def clamp(value, low, high):
    return max(low, min(high, value))


def money(amount):
    return f"${amount:,.2f}"


def slugify(text):
    """Convert text to a URL-friendly slug."""
    import re
    # Lowercase the text
    text = text.lower()
    # Replace every run of non-alphanumeric characters with a single '-'
    text = re.sub(r'[^a-z0-9]+', '-', text)
    # Strip leading and trailing '-'
    text = text.strip('-')
    return text
