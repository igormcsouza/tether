class PhoneNumber:
    def __init__(self, phone_number):
        # Check for letters
        if any(c.isalpha() for c in phone_number):
            raise ValueError("letters not permitted")
        
        # Remove all non-digit characters
        cleaned = ''.join(c for c in phone_number if c.isdigit())
        
        # Check for punctuation (anything that's not a digit or space or + or - or . or () or whitespace)
        # Actually, we need to check if there's punctuation in place of digits
        # The test "523-@:!-7890" should fail with "punctuations not permitted"
        # So we need to check if there are any characters that are not digits, spaces, +, -, ., (, )
        for c in phone_number:
            if c not in '0123456789 .-+()':
                raise ValueError("punctuations not permitted")
        
        # Check digit count
        if len(cleaned) < 10:
            raise ValueError("must not be fewer than 10 digits")
        
        if len(cleaned) > 11:
            raise ValueError("must not be greater than 11 digits")
        
        # Handle 11-digit numbers (must start with 1)
        if len(cleaned) == 11:
            if cleaned[0] != '1':
                raise ValueError("11 digits must start with 1")
            cleaned = cleaned[1:]  # Remove the country code
        
        # Now we should have exactly 10 digits
        if len(cleaned) != 10:
            raise ValueError("must not be fewer than 10 digits")
        
        # Extract area code (first 3 digits) and exchange code (next 3 digits)
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