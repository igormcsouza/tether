class StackUnderflowError(Exception):
    """Exception raised when Stack is not full.
       message: explanation of the error.
    """
    def __init__(self, message):
        self.message = message


def evaluate(input_data):
    """Evaluate Forth code and return the final stack."""
    stack = []
    # Dictionary to store user-defined words
    # Key is lowercase word name, value is the definition list (preserving case)
    words = {}
    
    # Process each line
    for line in input_data:
        # Check if this is a word definition
        if line.startswith(':'):
            # Parse the definition
            # Find the semicolon
            semicolon_pos = line.find(';')
            if semicolon_pos == -1:
                raise ValueError("undefined operation")
            
            # Extract the word name and definition
            definition_part = line[1:semicolon_pos]
            tokens = definition_part.split()
            word_name = tokens[0]
            definition = tokens[1:]
            
            # Check if word name is a number (illegal)
            try:
                # Handle negative numbers
                if word_name.startswith('-') and word_name[1:].isdigit():
                    int(word_name)
                elif word_name.isdigit():
                    int(word_name)
                else:
                    raise ValueError("illegal operation")
            except ValueError:
                pass  # Not a number, so it's valid
            
            # Store the definition (key is lowercase for case-insensitivity)
            words[word_name.lower()] = definition
        else:
            # Process the line as regular Forth code
            tokens = line.split()
            for token in tokens:
                token_lower = token.lower()
                process_token(stack, token_lower, words)
    
    return stack


def process_token(stack, token, words):
    """Process a single token."""
    # Check if it's a number
    try:
        # Handle negative numbers
        if token.startswith('-') and token[1:].isdigit():
            stack.append(int(token))
        elif token.isdigit():
            stack.append(int(token))
        else:
            raise ValueError("illegal operation")
        return
    except ValueError:
        pass
    
    # It's a word - handle built-in operations
    if token == '+':
        if len(stack) < 2:
            raise StackUnderflowError("Insufficient number of items in stack")
        b = stack.pop()
        a = stack.pop()
        stack.append(a + b)
    elif token == '-':
        if len(stack) < 2:
            raise StackUnderflowError("Insufficient number of items in stack")
        b = stack.pop()
        a = stack.pop()
        stack.append(a - b)
    elif token == '*':
        if len(stack) < 2:
            raise StackUnderflowError("Insufficient number of items in stack")
        b = stack.pop()
        a = stack.pop()
        stack.append(a * b)
    elif token == '/':
        if len(stack) < 2:
            raise StackUnderflowError("Insufficient number of items in stack")
        b = stack.pop()
        a = stack.pop()
        if b == 0:
            raise ZeroDivisionError("divide by zero")
        stack.append(int(a / b))
    elif token == 'dup':
        if len(stack) < 1:
            raise StackUnderflowError("Insufficient number of items in stack")
        stack.append(stack[-1])
    elif token == 'drop':
        if len(stack) < 1:
            raise StackUnderflowError("Insufficient number of items in stack")
        stack.pop()
    elif token == 'swap':
        if len(stack) < 2:
            raise StackUnderflowError("Insufficient number of items in stack")
        b = stack.pop()
        a = stack.pop()
        stack.append(b)
        stack.append(a)
    elif token == 'over':
        if len(stack) < 2:
            raise StackUnderflowError("Insufficient number of items in stack")
        stack.append(stack[-2])
    elif token in words:
        # It's a user-defined word - expand it
        definition = words[token]
        for def_token in definition:
            def_token_lower = def_token.lower()
            process_token(stack, def_token_lower, words)
    else:
        raise ValueError("undefined operation")