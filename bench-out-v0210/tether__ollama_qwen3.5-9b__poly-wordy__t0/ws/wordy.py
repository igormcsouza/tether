def answer(question):
    # Remove "What is " prefix and "?" suffix
    question = question.strip()
    
    # Check if it starts with "What is "
    if not question.startswith("What is "):
        raise ValueError("unknown operation")
    
    # Remove the prefix and suffix
    expression = question[8:-1].strip()
    
    # Split the expression into tokens
    tokens = expression.split()
    
    if len(tokens) == 0:
        raise ValueError("syntax error")
    
    # Parse the tokens
    # Format: number, operator, number, operator, number, ...
    # We need at least 1 token (just a number)
    
    # Check if we have valid tokens
    if len(tokens) < 1:
        raise ValueError("syntax error")
    
    # Parse first number
    try:
        result = int(tokens[0])
    except ValueError:
        raise ValueError("syntax error")
    
    i = 1
    while i < len(tokens):
        # Get the operator
        operator = tokens[i]
        
        # Check for valid operators
        if operator == "plus":
            if i + 1 >= len(tokens):
                raise ValueError("syntax error")
            try:
                operand = int(tokens[i + 1])
            except ValueError:
                raise ValueError("syntax error")
            result += operand
            i += 2
        elif operator == "minus":
            if i + 1 >= len(tokens):
                raise ValueError("syntax error")
            try:
                operand = int(tokens[i + 1])
            except ValueError:
                raise ValueError("syntax error")
            result -= operand
            i += 2
        elif operator == "multiplied":
            # "multiplied by" is two words
            if i + 2 >= len(tokens) or tokens[i + 1] != "by":
                raise ValueError("syntax error")
            try:
                operand = int(tokens[i + 2])
            except ValueError:
                raise ValueError("syntax error")
            result *= operand
            i += 3
        elif operator == "divided":
            # "divided by" is two words
            if i + 2 >= len(tokens) or tokens[i + 1] != "by":
                raise ValueError("syntax error")
            try:
                operand = int(tokens[i + 2])
            except ValueError:
                raise ValueError("syntax error")
            result //= operand
            i += 3
        else:
            # This could be a number (two numbers in a row) or unknown operation
            # Check if it's a number
            try:
                int(operator)
                # It's a number, so we have two numbers in a row - syntax error
                raise ValueError("syntax error")
            except ValueError:
                # It's not a number and not a valid operator - unknown operation
                raise ValueError("unknown operation")
    
    return result