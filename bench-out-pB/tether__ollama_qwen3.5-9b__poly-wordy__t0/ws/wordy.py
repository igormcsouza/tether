import re

def answer(question):
    # Remove "What is " prefix and "?" suffix
    question = question.strip()
    
    if not question.startswith("What is"):
        raise ValueError("unknown operation")
    
    # Remove "What is " and "?"
    question = question[7:-1].strip()
    
    if not question:
        raise ValueError("syntax error")
    
    # Split by spaces
    tokens = question.split()
    
    if not tokens:
        raise ValueError("syntax error")
    
    # First token should be a number
    if not re.match(r'^-?\d+$', tokens[0]):
        raise ValueError("syntax error")
    
    # Parse tokens into numbers and operations
    # Operations can be: "plus", "minus", "multiplied by", "divided by"
    # "multiplied by" and "divided by" are two tokens each
    
    numbers = []
    operations = []
    
    i = 0
    # First number
    numbers.append(int(tokens[0]))
    i = 1
    
    while i < len(tokens):
        # Check if this is a two-word operation
        if i + 1 < len(tokens) and tokens[i] in ['multiplied', 'divided'] and tokens[i+1] == 'by':
            op = tokens[i] + ' ' + tokens[i+1]
            operations.append(op)
            i += 2
        else:
            op = tokens[i]
            if op not in ['plus', 'minus', 'multiplied by', 'divided by']:
                # This is not a valid operation
                # Check if it's a number (syntax error - two numbers in a row)
                if re.match(r'^-?\d+$', op):
                    raise ValueError("syntax error")
                raise ValueError("unknown operation")
            operations.append(op)
            i += 1
        
        # Next token should be a number
        if i >= len(tokens):
            raise ValueError("syntax error")
        
        num_str = tokens[i]
        if not re.match(r'^-?\d+$', num_str):
            raise ValueError("syntax error")
        
        numbers.append(int(num_str))
        i += 1
    
    # Check we have equal numbers and operations (one more number than operations)
    if len(numbers) != len(operations) + 1:
        raise ValueError("syntax error")
    
    # Evaluate left to right
    result = numbers[0]
    for j in range(len(operations)):
        op = operations[j]
        next_num = numbers[j + 1]
        
        if op == 'plus':
            result = result + next_num
        elif op == 'minus':
            result = result - next_num
        elif op == 'multiplied by':
            result = result * next_num
        elif op == 'divided by':
            result = result // next_num
    
    return result