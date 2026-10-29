def translate(text):
    """Translate text from English to Pig Latin."""
    words = text.split()
    translated_words = []
    
    for word in words:
        translated_words.append(_translate_word(word))
    
    return ' '.join(translated_words)


def _translate_word(word):
    """Translate a single word to Pig Latin."""
    vowels = set('aeiou')
    
    # Rule 1: Check if word starts with vowel, "xr", or "yt"
    if len(word) > 0 and word[0].lower() in vowels:
        return word + 'ay'
    
    if len(word) >= 2 and word[:2].lower() == 'xr':
        return word + 'ay'
    
    if len(word) >= 2 and word[:2].lower() == 'yt':
        return word + 'ay'
    
    # Find the split point
    i = 0
    while i < len(word):
        char = word[i].lower()
        if char in vowels:
            # Found a vowel, split here
            break
        if i + 1 < len(word) and word[i].lower() == 'q' and word[i+1].lower() == 'u':
            # Found "qu", split here (after "qu")
            i += 2
            break
        if char == 'y' and i > 0:
            # Found 'y' after consonants, treat as vowel
            break
        i += 1
    else:
        # No vowel or "qu" found, move all consonants
        return word + 'ay'
    
    # Split at position i
    prefix = word[:i]
    suffix = word[i:]
    return suffix + prefix + 'ay'


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        print(translate(sys.argv[1]))