class PhoneNumber:
    def __init__(self, phone_number):
        # Check for letters first
        if any(c.isalpha() for c in phone_number):
            raise ValueError("letters not permitted")
        
        # Remove all non-digit characters
        cleaned = ''.join(c for c in phone_number if c.isdigit())
        
        # Check for punctuation (any non-digit, non-space, non-parenthesis, non-hyphen, non-dot, non-plus)
        # Actually, we already removed non-digits, so if there were any punctuation, 
        # we need to check if the original had any punctuation that wasn't allowed
        # Let's check if there are any characters that are not digits, spaces, or valid separators
        for c in phone_number:
            if c not in '0123456789 ()-.+ ':
                raise ValueError("punctuations not permitted")
        
        # Check digit count
        if len(cleaned) < 10:
            raise ValueError("must not be fewer than 10 digits")
        if len(cleaned) > 11:
            raise ValueError("must not be greater than 11 digits")
        
        # Handle 11-digit numbers (with country code)
        if len(cleaned) == 11:
            if cleaned[0] != '1':
                raise ValueError("11 digits must start with 1")
            cleaned = cleaned[1:]  # Remove country code
        
        # Now we should have exactly 10 digits
        if len(cleaned) != 10:
            raise ValueError("must not be fewer than 10 digits")
        
        # Extract area code and exchange code
        area_code = cleaned[:3]
        exchange_code = cleaned[3:6]
        
        # Validate area code
        if area_code[0] == '0':
            raise ValueError("area code cannot start with zero")
        if area_code[0] == '1':
            raise ValueError("area code cannot start with one")
        
        # Validate exchange code
        if exchange_code[0] == '0':
            raise ValueError("exchange code cannot start with zero")
        if exchange_code[0] == '1':
            raise ValueError("exchange code cannot start with one")
        
        self._number = cleaned
    
    @property
    def number(self):
        return self._number
    
    @property
    def area_code(self):
        return self._number[:3]
    
    def pretty(self):
        return f"({self._number[:3]})-{self._number[3:6]}-{self._number[6:]}"