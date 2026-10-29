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
    
    # Check that record IDs are continuous from 0 to n-1
    n = len(sorted_records)
    for i, record in enumerate(sorted_records):
        if record.record_id != i:
            raise ValueError("Record id is invalid or out of order.")
    
    # Find the root (record_id == 0)
    root_record = sorted_records[0]
    
    # Validate root: parent_id must be 0
    if root_record.parent_id != 0:
        raise ValueError("Node parent_id should be smaller than it's record_id.")
    
    # Validate all records: parent_id must be < record_id (except root where parent_id == record_id == 0)
    for record in sorted_records:
        if record.record_id == 0:
            # Root node: parent_id must equal record_id (which is 0)
            if record.parent_id != record.record_id:
                raise ValueError("Node parent_id should be smaller than it's record_id.")
        else:
            # Non-root node: parent_id must be strictly less than record_id
            if record.parent_id > record.record_id:
                raise ValueError("Node parent_id should be smaller than it's record_id.")
            if record.parent_id == record.record_id:
                raise ValueError("Only root should have equal record and parent id.")
    
    # Build the tree
    # Create a mapping from record_id to Node
    node_map = {}
    for record in sorted_records:
        node_map[record.record_id] = Node(record.record_id)
    
    # Build parent-child relationships
    for record in sorted_records:
        parent_id = record.parent_id
        child_node = node_map[record.record_id]
        # Skip adding root as child of itself
        if record.record_id == 0:
            continue
        parent_node = node_map[parent_id]
        parent_node.children.append(child_node)
    
    return node_map[0]