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
    records.sort(key=lambda x: x.record_id)
    
    # Check that record IDs are continuous from 0 to n-1
    n = len(records)
    for i, record in enumerate(records):
        if record.record_id != i:
            raise ValueError("Record id is invalid or out of order.")
    
    # Find the root (record_id == 0)
    root_record = records[0]
    if root_record.record_id != 0:
        raise ValueError("Record id is invalid or out of order.")
    
    # Validate each record
    for record in records:
        if record.record_id == 0:
            # Root node: parent_id must equal record_id (which is 0)
            if record.parent_id != 0:
                raise ValueError("Node parent_id should be smaller than it's record_id.")
        else:
            # Non-root nodes: parent_id must be smaller than record_id
            if record.parent_id >= record.record_id:
                if record.parent_id == record.record_id:
                    raise ValueError("Only root should have equal record and parent id.")
                else:
                    raise ValueError("Node parent_id should be smaller than it's record_id.")
    
    # Build the tree structure
    # Create a mapping from record_id to Node
    node_map = {}
    for record in records:
        node_map[record.record_id] = Node(record.record_id)
    
    # Build parent-child relationships
    for record in records:
        parent_id = record.parent_id
        if parent_id == record.record_id:
            # This is the root node
            continue
        # Add child to parent
        parent_node = node_map[parent_id]
        child_node = node_map[record.record_id]
        parent_node.children.append(child_node)
    
    return node_map[0]