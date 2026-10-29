def transpose(text):
    if not text:
        return ""
    
    lines = text.split('\n')
    max_length = max(len(line) for line in lines)
    
    # Pad each line on the left to match max_length
    padded_lines = [line.ljust(max_length) for line in lines]
    
    # Transpose
    result = []
    for j in range(max_length):
        row = ''.join(padded_lines[i][j] for i in range(len(lines)))
        result.append(row)
    
    return '\n'.join(result)