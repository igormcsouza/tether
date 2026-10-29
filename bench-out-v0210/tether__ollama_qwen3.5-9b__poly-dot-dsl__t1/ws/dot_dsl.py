class Node:
    """Represents a node in the graph."""
    
    def __init__(self, node_id, attributes):
        self.node_id = node_id
        self.attributes = attributes
    
    def __eq__(self, other):
        if not isinstance(other, Node):
            return False
        return self.node_id == other.node_id and self.attributes == other.attributes
    
    def __repr__(self):
        return f"Node({self.node_id!r}, {self.attributes!r})"


class Edge:
    """Represents an edge in the graph."""
    
    def __init__(self, node1_id, node2_id, attributes):
        self.node1_id = node1_id
        self.node2_id = node2_id
        self.attributes = attributes
    
    def __eq__(self, other):
        if not isinstance(other, Edge):
            return False
        return self.node1_id == other.node1_id and self.node2_id == other.node2_id and self.attributes == other.attributes
    
    def __repr__(self):
        return f"Edge({self.node1_id!r}, {self.node2_id!r}, {self.attributes!r})"


NODE = "NODE"
EDGE = "EDGE"
ATTR = "ATTR"


class Graph:
    """A graph data structure built with a DSL."""
    
    def __init__(self, items=None):
        self.nodes = []
        self.edges = []
        self.attrs = {}
        
        # Check if items is a valid iterable (list/tuple)
        if items is None:
            items = []
        elif not isinstance(items, (list, tuple)):
            raise TypeError("Graph data malformed")
        
        for item in items:
            self._process_item(item)
    
    def _process_item(self, item):
        """Process a single item in the graph definition."""
        
        # Check if item is iterable (tuple/list)
        if not isinstance(item, (tuple, list)):
            raise TypeError("Graph data malformed")
        
        # Check if item is empty or has only 1 element (incomplete)
        if len(item) < 2:
            raise TypeError("Graph item incomplete")
        
        item_type = item[0]
        
        if item_type == NODE:
            # NODE: (NODE, node_id, attributes)
            if len(item) != 3:
                raise ValueError("Node is malformed")
            node_id, attributes = item[1], item[2]
            if not isinstance(node_id, str):
                raise ValueError("Node is malformed")
            if not isinstance(attributes, dict):
                raise ValueError("Node is malformed")
            self.nodes.append(Node(node_id, attributes))
        
        elif item_type == EDGE:
            # EDGE: (EDGE, node1_id, node2_id, attributes)
            if len(item) != 4:
                raise ValueError("Edge is malformed")
            node1_id, node2_id, attributes = item[1], item[2], item[3]
            if not isinstance(node1_id, str):
                raise ValueError("Edge is malformed")
            if not isinstance(node2_id, str):
                raise ValueError("Edge is malformed")
            if not isinstance(attributes, dict):
                raise ValueError("Edge is malformed")
            self.edges.append(Edge(node1_id, node2_id, attributes))
        
        elif item_type == ATTR:
            # ATTR: (ATTR, attr_name, attr_value)
            if len(item) != 3:
                raise ValueError("Attribute is malformed")
            attr_name, attr_value = item[1], item[2]
            if not isinstance(attr_name, str):
                raise ValueError("Attribute is malformed")
            self.attrs[attr_name] = attr_value
        
        else:
            raise ValueError("Unknown item")