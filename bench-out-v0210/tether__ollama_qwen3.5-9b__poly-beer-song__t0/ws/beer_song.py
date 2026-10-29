def recite(start, take=1):
    """Recite verses from the beer song.
    
    Args:
        start: Starting number of bottles
        take: Number of verses to recite (default 1)
    
    Returns:
        List of verse strings
    """
    verses = []
    for i in range(take):
        n = start - i
        verse = verse_for_bottles(n)
        verses.append(verse)
    
    return verses


def verse_for_bottles(n):
    """Generate a single verse for the given number of bottles."""
    if n == 0:
        return (
            "No more bottles of beer on the wall, no more bottles of beer.\n"
            "Go to the store and buy some more, 99 bottles of beer on the wall."
        )
    elif n == 1:
        return (
            "1 bottle of beer on the wall, 1 bottle of beer.\n"
            "Take it down and pass it around, no more bottles of beer on the wall."
        )
    elif n == 2:
        return (
            "2 bottles of beer on the wall, 2 bottles of beer.\n"
            "Take one down and pass it around, 1 bottle of beer on the wall."
        )
    else:
        return (
            f"{n} bottles of beer on the wall, {n} bottles of beer.\n"
            f"Take one down and pass it around, {n-1} bottles of beer on the wall."
        )