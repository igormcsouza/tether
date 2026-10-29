import argparse
import re
import sys


def grep(pattern, flags, files):
    """
    Search for pattern in files and return matching lines.
    
    Args:
        pattern: The string to search for
        flags: Space-separated flags string
        files: List of file names to search in
    
    Returns:
        String containing matching lines with appropriate formatting
    """
    # Parse flags
    flag_list = flags.split() if flags else []
    use_line_numbers = '-n' in flag_list
    use_file_names_only = '-l' in flag_list
    case_insensitive = '-i' in flag_list
    invert_match = '-v' in flag_list
    match_entire_line = '-x' in flag_list
    
    # Prepare the pattern for matching
    # For case insensitive, we need to handle the comparison differently
    if case_insensitive:
        # Convert pattern to lowercase for matching
        pattern_lower = pattern.lower()
    else:
        pattern_lower = None
    
    # Build regex pattern
    if match_entire_line:
        regex_pattern = '^' + re.escape(pattern) + '$'
    else:
        regex_pattern = re.escape(pattern)
    
    compiled_regex = re.compile(regex_pattern, re.IGNORECASE if case_insensitive else 0)
    
    results = []
    file_names_added = set()  # Track which files have been added for -l flag
    
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
            is_match = compiled_regex.search(line_content) is not None
            
            # Apply invert flag
            if invert_match:
                is_match = not is_match
            
            if is_match:
                has_match = True
                
                # Build output line
                output_parts = []
                
                if use_file_names_only:
                    # Just output filename and newline
                    # Only add if not already added for this file
                    if filename not in file_names_added:
                        results.append(filename + '\n')
                        file_names_added.add(filename)
                else:
                    # Add filename if multiple files
                    if len(files) > 1:
                        output_parts.append(filename + ':')
                    
                    # Add line number if requested
                    if use_line_numbers:
                        output_parts.append(str(line_num) + ':')
                    
                    # Add the line content
                    output_parts.append(line_content)
                    
                    results.append(''.join(output_parts) + '\n')
    
    return ''.join(results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('pattern', help='Pattern to search for')
    parser.add_argument('flags', nargs='*', help='Flags')
    parser.add_argument('files', nargs='+', help='Files to search in')
    args = parser.parse_args()
    
    result = grep(args.pattern, ' '.join(args.flags), args.files)
    print(result, end='')