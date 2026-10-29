def transpose(text):
    if not text:
        return ""
    
    lines = text.split('\n')
    max_len = max(len(line) for line in lines)
    
    # Transpose: for each column index, collect characters from each row
    result = []
    for col_idx in range(max_len):
        row_chars = []
        for line in lines:
            if col_idx < len(line):
                row_chars.append(line[col_idx])
            else:
                row_chars.append(' ')
        # Strip trailing spaces from the output row
        result.append(''.join(row_chars).rstrip())
    
    return '\n'.join(result)