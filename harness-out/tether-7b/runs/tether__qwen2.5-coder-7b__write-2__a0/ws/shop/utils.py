def slugify(text):
    import re
    return re.sub(r'[^a-zA-Z0-9]+', '-', text.strip().lower())
