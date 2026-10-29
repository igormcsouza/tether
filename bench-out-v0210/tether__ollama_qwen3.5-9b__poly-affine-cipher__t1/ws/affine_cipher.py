import math

def encode(plaintext, a, b):
    """Encode plaintext using affine cipher."""
    # Check if a and m (26) are coprime
    if math.gcd(a, 26) != 1:
        raise ValueError("a and m must be coprime.")
    
    # Filter to keep only alphanumeric characters
    filtered = ''.join(c for c in plaintext if c.isalnum())
    
    # Encode each character
    encoded_chars = []
    for c in filtered:
        if c.isdigit():
            encoded_chars.append(c)
        else:
            # Convert letter to 0-25 range
            x = ord(c.lower()) - ord('a')
            # Apply encryption: E(x) = (ax + b) mod 26
            y = (a * x + b) % 26
            # Convert back to letter
            encoded_chars.append(chr(y + ord('a')))
    
    # Group into chunks of 5
    result = ''.join(encoded_chars)
    grouped = ' '.join(result[i:i+5] for i in range(0, len(result), 5))
    
    return grouped


def decode(ciphertext, a, b):
    """Decode ciphertext using affine cipher."""
    # Check if a and m (26) are coprime
    if math.gcd(a, 26) != 1:
        raise ValueError("a and m must be coprime.")
    
    # Find modular multiplicative inverse of a mod 26
    mmi = find_mmi(a, 26)
    
    # Filter to keep only alphanumeric characters
    filtered = ''.join(c for c in ciphertext if c.isalnum())
    
    # Decode each character
    decoded_chars = []
    for c in filtered:
        if c.isdigit():
            decoded_chars.append(c)
        else:
            # Convert letter to 0-25 range
            y = ord(c.lower()) - ord('a')
            # Apply decryption: D(y) = a^(-1)(y - b) mod 26
            x = (mmi * (y - b)) % 26
            # Convert back to letter
            decoded_chars.append(chr(x + ord('a')))
    
    return ''.join(decoded_chars)


def find_mmi(a, m):
    """Find the modular multiplicative inverse of a mod m."""
    for x in range(1, m):
        if (a * x) % m == 1:
            return x
    return None