from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class SgfTree:
    properties: Dict[str, List[str]]
    children: List['SgfTree'] = None
    
    def __post_init__(self):
        if self.children is None:
            self.children = []


def parse(sgf_string: str) -> SgfTree:
    """Parse an SGF string and return an SgfTree."""
    if not sgf_string or sgf_string.strip() == "":
        raise ValueError("tree missing")
    
    # Remove outer parentheses if present
    sgf_string = sgf_string.strip()
    
    if not sgf_string.startswith("("):
        raise ValueError("tree missing")
    
    # Find the matching closing parenthesis for the root
    root_end = find_matching_paren(sgf_string, 0)
    if root_end == -1:
        raise ValueError("tree missing")
    
    root_content = sgf_string[1:root_end]
    
    if root_content == "":
        raise ValueError("tree with no nodes")
    
    # Parse the root node
    root_tree = parse_node(root_content)
    
    return root_tree


def find_matching_paren(s: str, start: int) -> int:
    """Find the index of the matching closing parenthesis, handling escapes."""
    depth = 0
    i = start
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            # Escaped character - skip both
            i += 2
            continue
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def parse_node(content: str) -> SgfTree:
    """Parse a single node from SGF content."""
    # Remove leading semicolon if present (indicates a new node)
    content = content.lstrip(";")
    
    if not content:
        return SgfTree(properties={})
    
    # Find the end of this node's content
    node_end = find_matching_paren(content, 0)
    if node_end == -1:
        raise ValueError("tree missing")
    
    node_content = content[1:node_end]
    
    # Parse properties
    properties = parse_properties(node_content)
    
    # Parse children
    remaining = content[node_end + 1:]
    children = []
    while remaining:
        remaining = remaining.lstrip()
        if not remaining:
            break
        child_end = find_matching_paren(remaining, 0)
        if child_end == -1:
            raise ValueError("tree missing")
        child_content = remaining[1:child_end]
        children.append(parse_node(child_content))
        remaining = remaining[child_end + 1:]
    
    return SgfTree(properties=properties, children=children)


def parse_properties(content: str) -> Dict[str, List[str]]:
    """Parse properties from a node's content."""
    properties = {}
    i = 0
    
    while i < len(content):
        # Skip whitespace
        while i < len(content) and content[i] in " \t":
            i += 1
        
        if i >= len(content):
            break
        
        # Property key must be uppercase
        key_start = i
        while i < len(content) and content[i] not in "[];":
            i += 1
        
        key = content[key_start:i]
        
        if not key:
            raise ValueError("properties without delimiter")
        
        # Check if key is uppercase
        if key != key.upper():
            raise ValueError("property must be in uppercase")
        
        # Find the value
        if i >= len(content) or content[i] != "[":
            raise ValueError("properties without delimiter")
        i += 1  # Skip '['
        
        value_start = i
        while i < len(content) and content[i] != "]":
            i += 1
        
        if i >= len(content):
            raise ValueError("properties without delimiter")
        
        value = content[value_start:i]
        value = unescape_value(value)
        
        if key not in properties:
            properties[key] = []
        properties[key].append(value)
        
        i += 1  # Skip ']'
    
    return properties


def unescape_value(value: str) -> str:
    """Unescape an SGF property value."""
    result = []
    i = 0
    
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            next_char = value[i + 1]
            if next_char in " \t\n":
                # Escaped whitespace - remove it
                i += 2
            else:
                # Escaped non-whitespace - keep it as-is
                result.append(next_char)
                i += 2
        else:
            result.append(value[i])
            i += 1
    
    # Convert all whitespace (except newlines) to spaces
    result_str = "".join(result)
    # Replace tabs and other whitespace with spaces, but keep newlines
    final_result = []
    for char in result_str:
        if char == '\t' or char == '\r' or char in ' \f':
            final_result.append(' ')
        else:
            final_result.append(char)
    
    return "".join(final_result)