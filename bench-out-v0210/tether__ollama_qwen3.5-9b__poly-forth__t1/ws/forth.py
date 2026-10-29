class StackUnderflowError(Exception):
    """Exception raised when Stack is not full."""
    def __init__(self, message):
        self.message = message
        super().__init__(message)


def evaluate(input_data):
    """Evaluate a Forth program."""
    stack = []
    words = {}
    
    # Built-in operations
    def add():
        if len(stack) < 2:
            raise StackUnderflowError("Insufficient number of items in stack")
        b = stack.pop()
        a = stack.pop()
        stack.append(a + b)
    
    def sub():
        if len(stack) < 2:
            raise StackUnderflowError("Insufficient number of items in stack")
        b = stack.pop()
        a = stack.pop()
        stack.append(a - b)
    
    def mul():
        if len(stack) < 2:
            raise StackUnderflowError("Insufficient number of items in stack")
        b = stack.pop()
        a = stack.pop()
        stack.append(a * b)
    
    def div():
        if len(stack) < 2:
            raise StackUnderflowError("Insufficient number of items in stack")
        b = stack.pop()
        a = stack.pop()
        if b == 0:
            raise ZeroDivisionError("divide by zero")
        stack.append(a // b)
    
    def dup():
        if not stack:
            raise StackUnderflowError("Insufficient number of items in stack")
        stack.append(stack[-1])
    
    def drop():
        if not stack:
            raise StackUnderflowError("Insufficient number of items in stack")
        stack.pop()
    
    def swap():
        if len(stack) < 2:
            raise StackUnderflowError("Insufficient number of items in stack")
        b = stack.pop()
        a = stack.pop()
        stack.append(b)
        stack.append(a)
    
    def over():
        if len(stack) < 2:
            raise StackUnderflowError("Insufficient number of items in stack")
        stack.append(stack[-2])
    
    builtins = {
        '+': add,
        '-': sub,
        '*': mul,
        '/': div,
        'dup': dup,
        'drop': drop,
        'swap': swap,
        'over': over,
    }
    
    tokens = []
    for item in input_data:
        tokens.extend(item.split())
    
    i = 0
    while i < len(tokens):
        token = tokens[i]
        
        if token == ':':
            j = i + 1
            while j < len(tokens) and tokens[j] != ';':
                j += 1
            
            if j >= len(tokens):
                raise ValueError("undefined operation")
            
            word_name = tokens[i + 1]
            definition = tokens[i + 2:j]
            
            # Check if word_name is a number (illegal)
            if word_name.lstrip('-').isdigit():
                raise ValueError("illegal operation")
            
            # Normalize definition to lowercase
            normalized_def = [w.lower() for w in definition]
            words[word_name.lower()] = normalized_def
            
            i = j + 1
        else:
            token_lower = token.lower()
            
            if token_lower in builtins:
                builtins[token_lower]()
            elif token.lstrip('-').isdigit():
                stack.append(int(token))
            elif token_lower in words:
                for def_token in words[token_lower]:
                    execute_token(def_token)
            else:
                raise ValueError("undefined operation")
            i += 1
    
    return stack


def execute_token(token):
    """Execute a single token."""
    token_lower = token.lower()
    
    if token_lower in builtins:
        builtins[token_lower]()
    elif token.lstrip('-').isdigit():
        stack.append(int(token))
    elif token_lower in words:
        for def_token in words[token_lower]:
            execute_token(def_token)
    else:
        raise ValueError("undefined operation")


# Define builtins and words at module level
builtins = {
    '+': lambda: add(),
    '-': lambda: sub(),
    '*': lambda: mul(),
    '/': lambda: div(),
    'dup': lambda: dup(),
    'drop': lambda: drop(),
    'swap': lambda: swap(),
    'over': lambda: over(),
}
words = {}