class PhoneNumber:
    def __init__(self, phone_number):
        self._phone_number = phone_number
        self._cleaned_number = None
        self._validate()
    
    def _validate(self):
        # Check for letters
        if any(c.isalpha() for c in self._phone_number):
            raise ValueError("letters not permitted")
        
        # Remove all non-digit characters
        digits_only = ''.join(c for c in self._phone_number if c.isdigit())
        
        # Check for invalid punctuation (digits only should be all digits)
        # If there's any non-digit, non-letter character, it's invalid punctuation
        # Actually, we need to check if there are punctuation marks that aren't allowed
        # The test "523-@:!-7890" should raise "punctuations not permitted"
        # So we need to check for any character that is not a digit, letter, space, or +
        
        # Let's check for invalid punctuation
        for c in self._phone_number:
            if c.isalpha():
                raise ValueError("letters not permitted")
            if c not in '0123456789 +-().':
                raise ValueError("punctuations not permitted")
        
        # Now extract just digits
        digits_only = ''.join(c for c in self._phone_number if c.isdigit())
        
        # Check length
        if len(digits_only) < 10:
            raise ValueError("must not be fewer than 10 digits")
        if len(digits_only) > 11:
            raise ValueError("must not be greater than 11 digits")
        
        # If 11 digits, must start with 1
        if len(digits_only) == 11 and digits_only[0] != '1':
            raise ValueError("11 digits must start with 1")
        
        # Store cleaned number (remove country code if present)
        if len(digits_only) == 11:
            self._cleaned_number = digits_only[1:]
        else:
            self._cleaned_number = digits_only
        
        # Validate area code (first 3 digits)
        area_code = self._cleaned_number[0:3]
        if area_code[0] == '0':
            raise ValueError("area code cannot start with zero")
        if area_code[0] == '1':
            raise ValueError("area code cannot start with one")
        
        # Validate exchange code (next 3 digits)
        exchange_code = self._cleaned_number[3:6]
        if exchange_code[0] == '0':
            raise ValueError("exchange code cannot start with zero")
        if exchange_code[0] == '1':
            raise ValueError("exchange code cannot start with one")
    
    @property
    def number(self):
        return self._cleaned_number
    
    @property
    def area_code(self):
        return self._cleaned_number[0:3]
    
    def pretty(self):
        return f"({self.area_code})-{self._cleaned_number[3:6]}-{self._cleaned_number[6:]}"