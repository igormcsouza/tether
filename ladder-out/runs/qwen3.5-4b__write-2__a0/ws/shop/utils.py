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
    # Replace any sequence of non-alphanumeric characters with a single '-'
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', text.lower())
    # Strip leading and trailing '-'
    return slug.strip('-')