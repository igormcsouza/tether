def answer(question):
    # Remove "What is " prefix and "?" suffix
    question = question.replace("What is ", "").replace("?", "")
    
    # Split into tokens
    tokens = question.split()
    
    if len(tokens) < 1:
        raise ValueError("syntax error")
    
    # Extract numbers and operators with state tracking
    numbers = []
    operators = []
    i = 0
    
    # First token must be a number
    if len(tokens) > 0:
        try:
            num = int(tokens[0])
            numbers.append(num)
            i = 1
        except ValueError:
            raise ValueError("syntax error")
    
    # Then we expect: operator, number, operator, number, ...
    while i < len(tokens):
        # Expect an operator
        token = tokens[i]
        
        # Check for multi-word operators
        if i + 1 < len(tokens):
            two_word = tokens[i] + " " + tokens[i + 1]
            if two_word == "multiplied by":
                operators.append("*")
                i += 2
                continue
            elif two_word == "divided by":
                operators.append("/")
                i += 2
                continue
        
        # Single word operator
        if token == "plus":
            operators.append("+")
        elif token == "minus":
            operators.append("-")
        else:
            raise ValueError("unknown operation")
        
        i += 1
        
        # Expect a number after operator
        if i >= len(tokens):
            raise ValueError("syntax error")
        
        try:
            num = int(tokens[i])
            numbers.append(num)
            i += 1
        except ValueError:
            raise ValueError("syntax error")
    
    # Validate we have at least one operator (unless just a single number)
    if len(operators) == 0 and len(numbers) > 1:
        raise ValueError("syntax error")
    
    # Evaluate left to right
    result = numbers[0]
    for i, op in enumerate(operators):
        if op == "+":
            result += numbers[i + 1]
        elif op == "-":
            result -= numbers[i + 1]
        elif op == "*":
            result *= numbers[i + 1]
        elif op == "/":
            result = int(result / numbers[i + 1])  # Integer division
    
    return result