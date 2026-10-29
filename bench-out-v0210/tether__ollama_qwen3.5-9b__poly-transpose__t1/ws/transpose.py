def transpose(text):
    if not text:
        return ""
    
    lines = text.split('\n')
    max_len = max(len(line) for line in lines)
    
    result = []
    for col in range(max_len):
        transposed_row = []
        for line in lines:
            if col < len(line):
                transposed_row.append(line[col])
            else:
                transposed_row.append(' ')
        # Strip trailing spaces from the transposed row
        transposed_row_str = ''.join(transposed_row).rstrip(' ')
        result.append(transposed_row_str)
    
    return '\n'.join(result)