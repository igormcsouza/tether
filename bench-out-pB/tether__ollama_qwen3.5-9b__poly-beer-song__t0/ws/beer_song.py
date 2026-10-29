def recite(start, take=1):
    """Recite verses from 99 Bottles of Beer on the Wall."""
    verses = []
    for i in range(take):
        current = start - i
        next_bottle = current - 1
        
        if current == 0:
            # Last verse (0 bottles)
            line1 = "No more bottles of beer on the wall, no more bottles of beer."
            line2 = "Go to the store and buy some more, 99 bottles of beer on the wall."
        elif current == 1:
            # Verse with 1 bottle
            line1 = "1 bottle of beer on the wall, 1 bottle of beer."
            line2 = "Take it down and pass it around, no more bottles of beer on the wall."
        elif next_bottle == 1:
            # Verse with 2 bottles (next is 1, singular)
            line1 = f"{current} bottles of beer on the wall, {current} bottles of beer."
            line2 = f"Take one down and pass it around, 1 bottle of beer on the wall."
        else:
            # Generic verse
            line1 = f"{current} bottles of beer on the wall, {current} bottles of beer."
            line2 = f"Take one down and pass it around, {next_bottle} bottles of beer on the wall."
        
        verses.append(line1)
        verses.append(line2)
        
        # Add empty line between verses (but not after the last one)
        if i < take - 1:
            verses.append("")
    
    return verses