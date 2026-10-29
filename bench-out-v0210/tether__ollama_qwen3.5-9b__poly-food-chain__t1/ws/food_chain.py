def recite(start_verse, end_verse):
    """
    Generate the lyrics of the song 'I Know an Old Lady Who Swallowed a Fly'.
    
    Args:
        start_verse: The starting verse number (1-8)
        end_verse: The ending verse number (1-8)
    
    Returns:
        A list of strings representing the lyrics
    """
    animals = [
        "fly",
        "spider",
        "bird",
        "cat",
        "dog",
        "goat",
        "cow",
        "horse",
    ]
    
    # Special reactions for each animal
    reactions = [
        "",  # fly - no special reaction
        "It wriggled and jiggled and tickled inside her.",  # spider
        "How absurd to swallow a bird!",  # bird
        "Imagine that, to swallow a cat!",  # cat
        "What a hog, to swallow a dog!",  # dog
        "Just opened her throat and swallowed a goat!",  # goat
        "I don't know how she swallowed a cow!",  # cow
        "She's dead, of course!",  # horse
    ]
    
    result = []
    
    for i in range(start_verse, end_verse + 1):
        animal = animals[i - 1]
        reaction = reactions[i - 1]
        
        # First line
        result.append(f"I know an old lady who swallowed a {animal}.")
        
        # Special reaction line (except for fly)
        if reaction:
            result.append(reaction)
        
        # Chain lines (except for fly and horse)
        if i > 1 and i < 8:
            for j in range(i - 1, 0, -1):
                prev_animal = animals[j]
                next_animal = animals[j - 1]
                if prev_animal == "spider":
                    result.append(f"She swallowed the {prev_animal} to catch the fly.")
                else:
                    result.append(f"She swallowed the {prev_animal} to catch the {next_animal} that wriggled and jiggled and tickled inside her." if next_animal == "spider" else f"She swallowed the {prev_animal} to catch the {next_animal}.")
        
        # Last line for all verses except horse
        if i < 8:
            result.append("I don't know why she swallowed the fly. Perhaps she'll die.")
        
        # Empty line between verses (but not after the last verse)
        if i < end_verse:
            result.append("")
    
    return result