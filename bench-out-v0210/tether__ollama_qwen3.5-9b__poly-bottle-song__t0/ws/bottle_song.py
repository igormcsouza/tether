def recite(start, take=1):
    """
    Recite the Ten Green Bottles song.
    
    Args:
        start: The number of bottles to start with (1-10)
        take: The number of verses to return (default 1)
    
    Returns:
        A list of strings representing the song verses
    """
    result = []
    
    for i in range(take):
        current = start - i
        next_bottle = current - 1
        
        # Get the number word (capitalized for first line)
        number_word = number_to_word(current)
        # Get the bottle word (singular for 1)
        bottle_word = "bottle" if current == 1 else "bottles"
        # Get the next number word (lowercase for "There'll be...")
        if next_bottle == 0:
            next_word = "no"
        else:
            next_word = number_to_word_lower(next_bottle)
        # Get the next bottle word (singular for 1, plural otherwise)
        next_bottle_word = "bottle" if next_bottle == 1 else "bottles"
        
        # First line
        result.append(f"{number_word} green {bottle_word} hanging on the wall,")
        # Second line (same as first)
        result.append(f"{number_word} green {bottle_word} hanging on the wall,")
        # Third line
        result.append("And if one green bottle should accidentally fall,")
        # Fourth line
        if next_bottle == 0:
            result.append(f"There'll be no green {next_bottle_word} hanging on the wall.")
        else:
            result.append(f"There'll be {next_word} green {next_bottle_word} hanging on the wall.")
        
        # Add empty line between verses (but not after the last verse)
        if i < take - 1:
            result.append("")
    
    return result


def number_to_word(n):
    """Convert a number to its word representation (capitalized)."""
    words = {
        1: "One",
        2: "Two",
        3: "Three",
        4: "Four",
        5: "Five",
        6: "Six",
        7: "Seven",
        8: "Eight",
        9: "Nine",
        10: "Ten",
    }
    return words[n]


def number_to_word_lower(n):
    """Convert a number to its word representation (lowercase)."""
    words = {
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten",
    }
    return words[n]