def recite(start_verse, end_verse):
    """Generate the lyrics for the food chain song from start_verse to end_verse."""
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
    
    # Special reaction lines for each animal
    reactions = {
        "fly": "",
        "spider": "It wriggled and jiggled and tickled inside her.",
        "bird": "How absurd to swallow a bird!",
        "cat": "Imagine that, to swallow a cat!",
        "dog": "What a hog, to swallow a dog!",
        "goat": "Just opened her throat and swallowed a goat!",
        "cow": "I don't know how she swallowed a cow!",
        "horse": "She's dead, of course!",
    }
    
    result = []
    
    for i in range(start_verse - 1, end_verse):
        if i > start_verse - 1:
            result.append("")
        
        animal = animals[i]
        result.append(f"I know an old lady who swallowed a {animal}.")
        
        if animal == "fly":
            result.append("I don't know why she swallowed the fly. Perhaps she'll die.")
        elif animal == "horse":
            result.append(reactions["horse"])
        else:
            result.append(reactions[animal])
            
            # Build the chain
            for j in range(i, 0, -1):
                prev_animal = animals[j - 1]
                if j == 2:  # spider has special description
                    line = f"She swallowed the {animals[j]} to catch the {prev_animal} that wriggled and jiggled and tickled inside her."
                else:
                    line = f"She swallowed the {animals[j]} to catch the {prev_animal}."
                result.append(line)
            
            result.append("I don't know why she swallowed the fly. Perhaps she'll die.")
    
    return result