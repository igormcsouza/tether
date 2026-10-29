def grep(pattern, flags, files):
    """
    Search files for lines matching a search string and return all matching lines.
    
    Args:
        pattern: The string to search for
        flags: Zero or more flags as a string (e.g., "-n -i -x")
        files: One or more files to search in
    
    Returns:
        String containing matching lines
    """
    # Parse flags
    flag_list = flags.split() if flags else []
    use_line_numbers = "-n" in flag_list
    use_file_names_only = "-l" in flag_list
    case_insensitive = "-i" in flag_list
    invert_match = "-v" in flag_list
    match_entire_line = "-x" in flag_list
    
    # Build regex pattern
    if case_insensitive:
        pattern = pattern.lower()
    
    results = []
    
    for filename in files:
        try:
            with open(filename, 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            continue
        
        has_match = False
        
        for line_num, line in enumerate(lines, 1):
            # Remove trailing newline for comparison
            line_content = line.rstrip('\n')
            
            # Check if line matches
            if case_insensitive:
                line_content_lower = line_content.lower()
                pattern_lower = pattern.lower()
            else:
                line_content_lower = line_content
                pattern_lower = pattern
            
            # For -x flag, match entire line
            if match_entire_line:
                # For -x, we need to match the entire line
                # The pattern should match the whole line
                if case_insensitive:
                    match = line_content_lower == pattern_lower
                else:
                    match = line_content == pattern
            else:
                # Normal substring match
                if case_insensitive:
                    match = pattern_lower in line_content_lower
                else:
                    match = pattern in line_content
            
            # If -v flag, invert the match
            if invert_match:
                match = not match
            
            if match:
                has_match = True
                # Build output line
                output_parts = []
                
                # Add filename prefix if multiple files (and not using -l flag)
                if len(files) > 1 and not use_file_names_only:
                    output_parts.append(filename)
                
                if use_line_numbers:
                    output_parts.append(str(line_num))
                
                # Add the original line content (with newline)
                output_parts.append(line)
                
                results.append(':'.join(output_parts))
        
        # If -l flag and file has matches, add filename to results
        if use_file_names_only and has_match:
            results.append(filename)
    
    # If -l flag, we only want filenames, not the lines
    if use_file_names_only:
        return '\n'.join(results) + '\n' if results else ''
    
    # For normal output, join with newlines
    if results:
        return '\n'.join(results)
    else:
        return ''