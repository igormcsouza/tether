def translate(text):
    vowels = "aeiou"
    
    def translate_word(word):
        # Rule 1: If word begins with a vowel, or starts with "xr" or "yt"
        if word[0] in vowels:
            return word + "ay"
        
        if word.startswith("xr") or word.startswith("yt"):
            return word + "ay"
        
        # Find where to split the word
        i = 0
        while i < len(word):
            char = word[i]
            
            # Rule 3: Check for "qu"
            if i + 1 < len(word) and word[i:i+2] == "qu":
                # Move consonants before "qu" and "qu" to the end
                return word[i+2:] + word[:i+2] + "ay"
            
            # Rule 4: Check for "y" (treated as consonant at beginning)
            if char == "y" and i > 0:
                # "y" is treated as a vowel here (after consonants)
                break
            
            # Check for vowel
            if char in vowels:
                break
            
            i += 1
        
        # Rule 2: Move consonants to the end
        if i > 0:
            return word[i:] + word[:i] + "ay"
        
        # Shouldn't reach here, but just in case
        return word + "ay"
    
    # Process each word in the text
    words = text.split()
    translated_words = [translate_word(word) for word in words]
    return " ".join(translated_words)