def recite(start, take=1):
    """
    Recite the beer song from start bottle down for take verses.
    
    Args:
        start: Starting number of bottles (99 to 0)
        take: Number of verses to return (default 1)
    
    Returns:
        List of strings representing the verses
    """
    result = []
    for i in range(take):
        current = start - i
        if current == 0:
            result.extend([
                "No more bottles of beer on the wall, no more bottles of beer.",
                "Go to the store and buy some more, 99 bottles of beer on the wall."
            ])
        elif current == 1:
            result.extend([
                "1 bottle of beer on the wall, 1 bottle of beer.",
                "Take it down and pass it around, no more bottles of beer on the wall."
            ])
        elif current == 2:
            result.extend([
                "2 bottles of beer on the wall, 2 bottles of beer.",
                "Take one down and pass it around, 1 bottle of beer on the wall."
            ])
        else:
            result.extend([
                f"{current} bottles of beer on the wall, {current} bottles of beer.",
                f"Take one down and pass it around, {current-1} bottles of beer on the wall."
            ])
        
        # Add empty string between verses (but not after the last one)
        if i < take - 1:
            result.append("")
    
    return result