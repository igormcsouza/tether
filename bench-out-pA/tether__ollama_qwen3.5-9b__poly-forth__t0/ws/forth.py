class StackUnderflowError(Exception):
    """Exception raised when Stack is not full.
       message: explanation of the error.
    """
    def __init__(self, message):
        self.message = message


def evaluate(input_data):
    stack = []
    definitions = {}
    
    for line in input_data:
        tokens = line.split()
        for token in tokens:
            if token == ':':
                # Start of word definition
                parse_definition(stack, definitions, tokens)
                break
            elif token == ';':
                # End of word definition (shouldn't happen here)
                pass
            elif token.lower() in definitions:
                # Execute user-defined word (case-insensitive lookup)
                execute_word(stack, definitions, token.lower())
            elif token.lower() in ('+', '-', '*', '/', 'dup', 'drop', 'swap', 'over'):
                # Execute built-in word (case-insensitive)
                execute_builtin(stack, token.lower())
            else:
                # Parse as number or word
                if is_number(token):
                    stack.append(int(token))
                else:
                    definitions[token.lower()] = []
    
    return stack


def is_number(s):
    """Check if string is a number (sequence of digits, possibly with leading minus)."""
    return s.isdigit() or (s.startswith('-') and s[1:].isdigit())


def parse_definition(stack, definitions, tokens):
    """Parse a word definition starting with ':'."""
    # Find the matching semicolon
    word_name = tokens[1].lower()
    
    # Check if word name is a number
    if is_number(word_name):
        raise ValueError("illegal operation")
    
    # Extract definition (everything between : and ;)
    definition = tokens[2:-1]
    
    # Parse the definition into tokens
    parsed_def = []
    for token in definition:
        if is_number(token):
            parsed_def.append(token)
        else:
            parsed_def.append(token.lower())
    
    definitions[word_name] = parsed_def


def execute_word(stack, definitions, word):
    """Execute a user-defined word."""
    if word not in definitions:
        raise ValueError("undefined operation")
    
    for token in definitions[word]:
        if token == ':':
            # Nested definition - not supported in this simple version
            # Just skip it
            continue
        elif token == ';':
            # End of definition
            break
        elif token in definitions:
            execute_word(stack, definitions, token)
        elif token in ('+', '-', '*', '/', 'dup', 'drop', 'swap', 'over'):
            execute_builtin(stack, token)
        else:
            if is_number(token):
                stack.append(int(token))
            else:
                definitions[token.lower()] = []


def execute_builtin(stack, token):
    """Execute a built-in word."""
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
        # over copies the second element from the top (stack[1])
        stack.append(stack[1])