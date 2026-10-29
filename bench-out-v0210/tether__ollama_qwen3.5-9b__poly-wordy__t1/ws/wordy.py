def answer(question):
    # Remove "What is " prefix and "?" suffix
    if not question.startswith("What is "):
        raise ValueError("unknown operation")
    
    # Remove the prefix and suffix
    expr = question[8:-1]  # "What is " is 8 chars, "?" is 1 char
    
    # Split by spaces to get tokens
    tokens = expr.split()
    
    if not tokens:
        raise ValueError("syntax error")
    
    # Parse the expression
    # Format: number operator number operator number ...
    # Operators can be single word or multi-word: "plus", "minus", "multiplied by", "divided by"
    
    numbers = []
    operators = []
    
    i = 0
    while i < len(tokens):
        token = tokens[i]
        
        # Check if it's a number (possibly negative)
        # A number is either a digit or starts with - followed by digits
        if token.lstrip('-').isdigit() and (token[0] == '-' or token.isdigit()):
            numbers.append(int(token))
            i += 1
        elif token == 'plus':
            operators.append('plus')
            i += 1
        elif token == 'minus':
            operators.append('minus')
            i += 1
        elif token == 'multiplied':
            # Check if next token is "by"
            if i + 1 < len(tokens) and tokens[i + 1] == 'by':
                operators.append('multiplied by')
                i += 2  # Skip both parts
            else:
                raise ValueError("unknown operation")
        elif token == 'divided':
            # Check if next token is "by"
            if i + 1 < len(tokens) and tokens[i + 1] == 'by':
                operators.append('divided by')
                i += 2  # Skip both parts
            else:
                raise ValueError("unknown operation")
        else:
            raise ValueError("unknown operation")
    
    # Validate we have at least one number
    if not numbers:
        raise ValueError("syntax error")
    
    # If no operators, just return the single number
    if not operators:
        if len(numbers) == 1:
            return numbers[0]
        else:
            raise ValueError("syntax error")
    
    # Validate the structure: number, operator, number, operator, number...
    # Should be: [number, operator, number, operator, number, ...]
    # So we need len(operators) == len(numbers) - 1
    
    if len(operators) != len(numbers) - 1:
        raise ValueError("syntax error")
    
    # Check that the first token is a number (not an operator)
    # This catches prefix notation like "plus 1 2"
    # For multi-word operators, tokens[0] would be "multiplied" or "divided"
    if not tokens[0].lstrip('-').isdigit() and tokens[0] not in ['multiplied', 'divided']:
        raise ValueError("syntax error")
    
    # Now evaluate left-to-right
    result = numbers[0]
    
    for i, op in enumerate(operators):
        if op == "plus":
            result += numbers[i + 1]
        elif op == "minus":
            result -= numbers[i + 1]
        elif op == "multiplied by":
            result *= numbers[i + 1]
        elif op == "divided by":
            if numbers[i + 1] == 0:
                raise ValueError("syntax error")
            result = int(result / numbers[i + 1])
    
    return result