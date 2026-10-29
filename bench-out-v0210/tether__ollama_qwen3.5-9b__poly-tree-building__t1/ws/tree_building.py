class Record:
    def __init__(self, record_id, parent_id):
        self.record_id = record_id
        self.parent_id = parent_id


class Node:
    def __init__(self, node_id):
        self.node_id = node_id
        self.children = []


def BuildTree(records):
    # Handle empty list
    if not records:
        return None
    
    # Sort records by record_id
    sorted_records = sorted(records, key=lambda r: r.record_id)
    
    # Check that IDs are continuous from 0 to n-1
    n = len(sorted_records)
    for i, record in enumerate(sorted_records):
        if record.record_id != i:
            raise ValueError("Record id is invalid or out of order.")
    
    # Find root (record_id == 0)
    root_record = sorted_records[0]
    
    # Validate root: parent_id should be 0
    if root_record.parent_id != 0:
        raise ValueError("Node parent_id should be smaller than it's record_id.")
    
    # Build parent to children mapping
    parent_map = {}
    for i in range(n):
        parent_map[i] = []
    
    # Validate each record and build tree structure
    for record in sorted_records:
        record_id = record.record_id
        parent_id = record.parent_id
        
        # For root (record_id == 0), parent_id must be 0
        if record_id == 0:
            if parent_id != 0:
                raise ValueError("Node parent_id should be smaller than it's record_id.")
            continue
        
        # For non-root nodes, parent_id must be less than record_id
        if parent_id >= record_id:
            if parent_id == record_id:
                raise ValueError("Only root should have equal record and parent id.")
            else:
                raise ValueError("Node parent_id should be smaller than it's record_id.")
        
        # Add child to parent
        parent_map[parent_id].append(record)
    
    # Build the tree structure
    root = Node(root_record.record_id)
    
    def build_node(node_id):
        node = Node(node_id)
        for child_record in parent_map[node_id]:
            child = build_node(child_record.record_id)
            node.children.append(child)
        return node
    
    root = build_node(0)
    return root