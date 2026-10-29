import re

def grep(pattern, flags, files):
    """
    Search files for lines matching a search string.
    
    Args:
        pattern: The string to search for
        flags: Zero or more flags as a string (e.g., "-n -i -x")
        files: List of files to search in
    
    Returns:
        String containing matching lines with appropriate formatting
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
    
    # Prepare the regex
    if match_entire_line:
        # For -x, we need to match the entire line
        regex_pattern = "^" + re.escape(pattern) + "$"
    else:
        regex_pattern = re.escape(pattern)
    
    regex = re.compile(regex_pattern)
    
    results = []
    
    for filename in files:
        try:
            with open(filename, 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            continue
        
        file_has_match = False
        
        for line_num, line in enumerate(lines, 1):
            # Remove trailing newline for comparison but keep it for output
            line_content = line.rstrip('\n')
            
            # Check if line matches
            if invert_match:
                # For inverted match, we want lines that DON'T match
                if not regex.search(line_content):
                    file_has_match = True
                    match_line = line
                    if use_line_numbers:
                        match_line = f"{line_num}:{match_line}"
                    if use_file_names_only:
                        results.append(f"{filename}\n")
                    else:
                        results.append(f"{filename}:{match_line}")
            else:
                # Normal match
                if regex.search(line_content):
                    file_has_match = True
                    match_line = line
                    if use_line_numbers:
                        match_line = f"{line_num}:{match_line}"
                    if use_file_names_only:
                        results.append(f"{filename}\n")
                    else:
                        results.append(f"{filename}:{match_line}")
        
        # If -l flag and we found a match in this file, add filename to results
        # Only add if we haven't already added it for this file
        if use_file_names_only and file_has_match:
            # Check if we already added this filename
            if not any(r == filename + "\n" for r in results):
                results.append(f"{filename}\n")
    
    # If -l flag, we need to output just filenames, not the full lines
    if use_file_names_only:
        return "".join(results)
    
    # For non -l flag, we need to strip filename prefix for single file
    # and keep it for multiple files
    if len(files) == 1:
        # Single file - strip filename prefix
        stripped_results = []
        for result in results:
            # Remove "filename:" prefix
            if result.startswith(files[0] + ":"):
                stripped_results.append(result[len(files[0]) + 1:])
            else:
                stripped_results.append(result)
        return "".join(stripped_results)
    else:
        # Multiple files - keep filename prefix
        return "".join(results)