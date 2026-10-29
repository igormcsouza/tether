import re
import io


def grep(pattern, flags, files):
    """
    Search for pattern in files and return matching lines.
    
    Args:
        pattern: The string to search for
        flags: Space-separated flags string (e.g., "-n -i -x")
        files: List of file names to search in
    
    Returns:
        String of matching lines (or file names if -l flag)
    """
    # Parse flags
    flag_list = flags.split() if flags else []
    use_line_numbers = "-n" in flag_list
    use_file_names_only = "-l" in flag_list
    case_insensitive = "-i" in flag_list
    invert_match = "-v" in flag_list
    match_entire_line = "-x" in flag_list
    
    # Build regex pattern
    # Case-insensitive flag must be at the start
    if case_insensitive:
        regex_pattern = "(?i)" + re.escape(pattern)
    else:
        regex_pattern = re.escape(pattern)
    
    # Compile regex
    if match_entire_line:
        regex = re.compile(f"^{regex_pattern}$")
    else:
        regex = re.compile(regex_pattern)
    
    results = []
    
    for filename in files:
        try:
            with open(filename, 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            continue
        
        has_match = False
        
        for line_num, line in enumerate(lines, 1):
            # Remove trailing newline for matching
            line_content = line.rstrip('\n')
            
            # Check if line matches
            is_match = bool(regex.search(line_content))
            
            # Apply invert flag
            if invert_match:
                is_match = not is_match
            
            if is_match:
                has_match = True
        
        # If -l flag and file has matches, add filename to results
        if use_file_names_only and has_match:
            results.append(filename + "\n")
        elif not use_file_names_only:
            # Otherwise, output matching lines
            for line_num, line in enumerate(lines, 1):
                line_content = line.rstrip('\n')
                
                # Check if line matches
                is_match = bool(regex.search(line_content))
                
                # Apply invert flag
                if invert_match:
                    is_match = not is_match
                
                if is_match:
                    # Build output line
                    output_parts = []
                    
                    # Add filename if multiple files
                    if len(files) > 1:
                        output_parts.append(filename + ":")
                    
                    # Add line number if requested
                    if use_line_numbers:
                        output_parts.append(str(line_num) + ":")
                    
                    # Add the line content
                    output_parts.append(line_content)
                    
                    results.append("".join(output_parts) + "\n")
    
    return "".join(results)