def recite(start, take=1):
    """
    Recite verses from the beer song.
    
    Args:
        start: Starting number of bottles (99 to 0)
        take: Number of verses to recite (default 1)
    
    Returns:
        List of strings representing the lyrics
    """
    verses = []
    for i in range(take):
        n = start - i
        verse = get_verse(n)
        verses.extend(verse)
        if i < take - 1:
            verses.append("")
    return verses


def get_verse(n):
    """Get a single verse for the given number of bottles."""
    if n == 0:
        return [
            "No more bottles of beer on the wall, no more bottles of beer.",
            "Go to the store and buy some more, 99 bottles of beer on the wall."
        ]
    elif n == 1:
        return [
            "1 bottle of beer on the wall, 1 bottle of beer.",
            "Take it down and pass it around, no more bottles of beer on the wall."
        ]
    elif n == 2:
        return [
            "2 bottles of beer on the wall, 2 bottles of beer.",
            "Take one down and pass it around, 1 bottle of beer on the wall."
        ]
    else:
        return [
            f"{n} bottles of beer on the wall, {n} bottles of beer.",
            f"Take one down and pass it around, {n-1} bottles of beer on the wall."
        ]