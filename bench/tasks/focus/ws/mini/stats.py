"""Text statistics."""


def count_lines(text):
    return len(text.splitlines())


def count_words(text):
    return len(text.split())


def count_chars(text):
    return len(text)
