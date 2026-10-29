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
    
    # Check if record IDs are continuous from 0 to n-1
    n = len(sorted_records)
    for i, record in enumerate(sorted_records):
        if record.record_id != i:
            raise ValueError("Record id is invalid or out of order.")
    
    # Validate root node exists and has correct parent_id
    root = sorted_records[0]
    if root.record_id != 0:
        raise ValueError("Record id is invalid or out of order.")
    if root.parent_id != 0:
        raise ValueError("Node parent_id should be smaller than it's record_id.")
    
    # Build tree structure
    nodes = {}
    for record in sorted_records:
        nodes[record.record_id] = Node(record.record_id)
    
    # Connect children to parents
    for record in sorted_records:
        if record.record_id == 0:
            continue
        parent_id = record.parent_id
        if parent_id >= record.record_id:
            if parent_id == record.record_id:
                raise ValueError("Only root should have equal record and parent id.")
            else:
                raise ValueError("Node parent_id should be smaller than it's record_id.")
        nodes[parent_id].children.append(nodes[record.record_id])
    
    return nodes[0]
