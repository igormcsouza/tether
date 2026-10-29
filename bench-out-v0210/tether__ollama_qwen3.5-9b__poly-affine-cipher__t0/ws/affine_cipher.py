import math

def gcd(a, b):
    """Calculate the greatest common divisor."""
    while b:
        a, b = b, a % b
    return a

def encode(message, a, b):
    """Encode a message using the affine cipher."""
    # Validate that a and m (26) are coprime
    if gcd(a, 26) != 1:
        raise ValueError("a and m must be coprime.")
    
    # Filter out non-alphanumeric characters and convert to lowercase
    cleaned = ''.join(c for c in message.lower() if c.isalnum())
    
    # Encrypt each character
    encrypted = []
    for c in cleaned:
        if c.isdigit():
            encrypted.append(c)
        else:
            # Convert letter to index (0-25)
            i = ord(c) - ord('a')
            # Apply encryption formula: E(x) = (a*i + b) mod 26
            encrypted_i = (a * i + b) % 26
            # Convert back to letter
            encrypted.append(chr(encrypted_i + ord('a')))
    
    # Group into chunks of 5
    result = []
    for i in range(0, len(encrypted), 5):
        result.append(''.join(encrypted[i:i+5]))
    return ' '.join(result)

def decode(message, a, b):
    """Decode a message using the affine cipher."""
    # Validate that a and m (26) are coprime
    if gcd(a, 26) != 1:
        raise ValueError("a and m must be coprime.")
    
    # Find the modular multiplicative inverse of a mod 26
    mmi = None
    for x in range(1, 26):
        if (a * x) % 26 == 1:
            mmi = x
            break
    
    # Filter out non-alphanumeric characters and convert to lowercase
    cleaned = ''.join(c for c in message.lower() if c.isalnum())
    
    # Decrypt each character
    decrypted = []
    for c in cleaned:
        if c.isdigit():
            decrypted.append(c)
        else:
            # Convert letter to index (0-25)
            y = ord(c) - ord('a')
            # Apply decryption formula: D(y) = (a^-1)(y - b) mod 26
            decrypted_i = (mmi * (y - b)) % 26
            # Convert back to letter
            decrypted.append(chr(decrypted_i + ord('a')))
    
    return ''.join(decrypted)