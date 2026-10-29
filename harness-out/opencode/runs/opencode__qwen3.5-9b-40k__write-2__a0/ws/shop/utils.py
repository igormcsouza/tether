"""Small helpers."""

import re


def slugify(text):
    """Lowercase text, replace non-alphanumeric with '-', strip leading/trailing '.'."""
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')



def clamp(value, low, high):
    return max(low, min(high, value))


def money(amount):
    return f"${amount:,.2f}"
