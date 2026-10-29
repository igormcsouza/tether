def answer(question):
    # Remove "What is " prefix and "?" suffix
    question = question.strip()
    
    # Check for non-math questions
    if not question.startswith("What is"):
        raise ValueError("unknown operation")
    
    # Remove the prefix and suffix
    content = question[7:].strip()
    if content.endswith("?"):
        content = content[:-1].strip()
    
    if not content:
        raise ValueError("syntax error")
    
    # Split by spaces to get tokens
    tokens = content.split()
    
    if not tokens:
        raise ValueError("syntax error")
    
    # First token should be a number
    if not tokens[0].lstrip('-').isdigit():
        raise ValueError("unknown operation")
    
    # Expand multi-word operations
    expanded_tokens = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "multiplied" and i + 1 < len(tokens) and tokens[i + 1] == "by":
            expanded_tokens.append("multiplied by")
            i += 2
        elif tokens[i] == "divided" and i + 1 < len(tokens) and tokens[i + 1] == "by":
            expanded_tokens.append("divided by")
            i += 2
        else:
            expanded_tokens.append(tokens[i])
            i += 1
    
    # Now parse: number (operation number)*
    values = []
    ops = []
    
    # First token must be a number
    if not expanded_tokens[0].lstrip('-').isdigit():
        raise ValueError("unknown operation")
    
    values.append(int(expanded_tokens[0]))
    
    i = 1
    while i < len(expanded_tokens):
        # If we have a number where we expect an operation, it's a syntax error
        if expanded_tokens[i].lstrip('-').isdigit():
            raise ValueError("syntax error")
        
        op = expanded_tokens[i]
        
        # Check if this is a valid operation
        if op not in ("plus", "minus", "multiplied by", "divided by"):
            raise ValueError("unknown operation")
        
        ops.append(op)
        
        # Next token must be a number
        if i + 1 >= len(expanded_tokens):
            raise ValueError("syntax error")
        
        next_token = expanded_tokens[i + 1]
        if not next_token.lstrip('-').isdigit():
            raise ValueError("syntax error")
        
        values.append(int(next_token))
        i += 2
    
    # If there are no operations, just return the number
    if not ops:
        return values[0]
    
    # Evaluate left to right
    result = values[0]
    for j, op in enumerate(ops):
        if op == "plus":
            result += values[j + 1]
        elif op == "minus":
            result -= values[j + 1]
        elif op == "multiplied by":
            result *= values[j + 1]
        elif op == "divided by":
            result //= values[j + 1]  # Integer division
    
    return result