"""Small helpers."""


def clamp(value, low, high):
    return max(low, min(high, value))


def money(amount):
    return f"${amount:,.2f}"


def slugify(text):
    """Convert text to a URL-friendly slug.
    
    Lowercases the text, replaces every run of non-alphanumeric characters
    with a single '-', and strips leading and trailing '-'.
    """
    import re
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = text.strip('-')
    return text
