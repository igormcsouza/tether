def recite(start, take=1):
    """Recite the Ten Green Bottles song.
    
    Args:
        start: Number of bottles to start with (1-10)
        take: Number of verses to return (default 1)
    
    Returns:
        List of strings representing the verses
    """
    verses = []
    for i in range(take):
        current = start - i
        verses.extend(verse(current))
        if i < take - 1:
            verses.append("")
    return verses


def verse(n):
    """Generate a single verse for n bottles."""
    number = number_to_word(n)
    next_n = n - 1
    next_number = number_to_word(next_n).lower()
    
    first_line = f"{number} green {bottle_word(n)} hanging on the wall,"
    third_line = "And if one green bottle should accidentally fall,"
    fourth_line = f"There'll be {next_number} green {bottle_word(next_n)} hanging on the wall."
    
    return [first_line, first_line, third_line, fourth_line]


def number_to_word(n):
    """Convert a number to its word representation."""
    words = {
        10: "Ten",
        9: "Nine",
        8: "Eight",
        7: "Seven",
        6: "Six",
        5: "Five",
        4: "Four",
        3: "Three",
        2: "Two",
        1: "One",
        0: "no"
    }
    return words[n]


def bottle_word(n):
    """Get the correct bottle word (singular or plural)."""
    if n == 1:
        return "bottle"
    return "bottles"