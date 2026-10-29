from dataclasses import dataclass
from typing import Dict, List


@dataclass
class SgfTree:
    properties: Dict[str, List[str]]
    children: List['SgfTree'] = None
    
    def __post_init__(self):
        if self.children is None:
            self.children = []


def parse(sgf_string: str) -> SgfTree:
    """Parse an SGF string and return an SgfTree."""
    if not sgf_string:
        raise ValueError("tree missing")
    
    # Remove outer parentheses
    if not sgf_string.startswith('(') or not sgf_string.endswith(')'):
        raise ValueError("tree missing")
    
    inner = sgf_string[1:-1]
    
    if not inner:
        raise ValueError("tree with no nodes")
    
    return _parse_node(inner)


def _parse_node(s: str) -> SgfTree:
    """Parse a single node from the SGF string."""
    if not s:
        raise ValueError("tree missing")
    
    # Check if this is a child node (starts with ;)
    if s.startswith(';'):
        # This is a child node with no properties at this level
        # Parse the child
        child = _parse_node(s[1:])
        return SgfTree(properties={}, children=[child])
    
    # Parse properties
    properties = {}
    pos = 0
    children = []
    
    while pos < len(s):
        # Check for child node
        if s[pos] == ';':
            # Parse the child node
            child = _parse_node(s[pos:])
            children.append(child)
            return SgfTree(properties=properties, children=children)
        
        # Check for closing parenthesis
        if s[pos] == ')':
            return SgfTree(properties=properties, children=children)
        
        # Parse property name (uppercase letters)
        prop_name_start = pos
        while pos < len(s) and s[pos].isupper():
            pos += 1
        
        if prop_name_start == pos:
            raise ValueError("properties without delimiter")
        
        prop_name = s[prop_name_start:pos]
        
        # Check property name is uppercase
        if prop_name != prop_name.upper():
            raise ValueError("property must be in uppercase")
        
        # Parse property values
        while pos < len(s):
            if s[pos] == ';':
                # End of properties, move past semicolon
                pos += 1
                break
            if s[pos] == ')':
                return SgfTree(properties=properties, children=children)
            
            # Parse value
            if s[pos] == '[':
                # Find the closing bracket
                value_start = pos + 1
                value_end = _find_closing_bracket(s, value_start)
                if value_end == -1:
                    raise ValueError("tree missing")
                
                value = s[value_start:value_end]
                value = _process_value(value)
                
                if prop_name not in properties:
                    properties[prop_name] = []
                properties[prop_name].append(value)
                
                pos = value_end + 1
            else:
                # This shouldn't happen - property value must be in brackets
                raise ValueError("properties without delimiter")
        
        # Move past the semicolon
        if pos < len(s) and s[pos] == ';':
            pos += 1
    
    # If we get here, we didn't find any children
    return SgfTree(properties=properties, children=children)


def _find_closing_bracket(s: str, start: int) -> int:
    """Find the closing bracket, handling escaped brackets."""
    i = start
    while i < len(s):
        if s[i] == '\\':
            # Skip the escape character and the next character
            i += 2
        elif s[i] == ']':
            return i
        else:
            i += 1
    return -1


def _process_value(value: str) -> str:
    """Process an SGF text value according to the rules."""
    result = []
    i = 0
    while i < len(value):
        if value[i] == '\\' and i + 1 < len(value):
            # Escape character
            next_char = value[i + 1]
            if next_char == '\n':
                # Newline after escape is removed
                pass
            elif next_char in '\r\t ':
                # Other whitespace after escape is converted to space
                result.append(' ')
            else:
                # Non-whitespace after escape is inserted as-is
                result.append(next_char)
            i += 2
        else:
            result.append(value[i])
            i += 1
    
    # Convert all whitespace except newline to spaces
    result_str = ''.join(result)
    final_result = []
    for char in result_str:
        if char == '\n':
            final_result.append(char)
        elif char in ' \t\r':
            final_result.append(' ')
        else:
            final_result.append(char)
    
    return ''.join(final_result)