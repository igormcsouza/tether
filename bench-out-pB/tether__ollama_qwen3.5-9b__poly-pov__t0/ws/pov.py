from json import dumps


class Tree:
    def __init__(self, label, children=None):
        self.label = label
        self.children = children if children is not None else []

    def __dict__(self):
        return {self.label: [c.__dict__() for c in sorted(self.children)]}

    def __str__(self, indent=None):
        return dumps(self.__dict__(), indent=indent)

    def __lt__(self, other):
        return self.label < other.label

    def __eq__(self, other):
        return self.__dict__() == other.__dict__()

    def _find_node(self, label, parent=None):
        """Find a node by label, return (node, parent) or None if not found."""
        if self.label == label:
            return (self, parent)
        for child in self.children:
            result = child._find_node(label, self)
            if result:
                return result
        return None

    def _all_nodes(self):
        """Return all node labels in the tree."""
        result = [self.label]
        for child in self.children:
            result.extend(child._all_nodes())
        return result

    def from_pov(self, from_node):
        """Reparent the tree so that from_node becomes the root."""
        # Check if from_node exists
        result = self._find_node(from_node)
        if result is None:
            raise ValueError("Tree could not be reoriented")
        
        # If it's a singleton tree, return as is
        if len(self.children) == 0:
            return self
        
        # Find the node and its parent
        node, parent = result
        
        # If the node is already the root, return as is
        if parent is None:
            return self
        
        # Create a new tree rooted at from_node
        # The new root's children will be:
        # 1. The original children of from_node
        # 2. The former parent of from_node (with its other children)
        
        # First, create the new root with original children
        new_root = Tree(node.label, list(node.children))
        
        # Create a new parent node with its children (excluding from_node)
        # Sort the children to ensure consistent ordering
        new_parent_children = [c for c in parent.children if c.label != node.label]
        new_parent = Tree(parent.label, sorted(new_parent_children))
        
        # Add the new parent as a child of the new root
        new_root.children.append(new_parent)
        
        return new_root

    def path_to(self, from_node, to_node):
        """Find the path between two nodes."""
        # Check if from_node exists
        from_result = self._find_node(from_node)
        if from_result is None:
            raise ValueError("Tree could not be reoriented")
        
        # Check if to_node exists
        to_result = self._find_node(to_node)
        if to_result is None:
            raise ValueError("No path found")
        
        # Build a map of node label -> (node, parent)
        node_map = {}
        
        def build_node_map(node, parent=None):
            node_map[node.label] = (node, parent)
            for child in node.children:
                build_node_map(child, node)
        
        build_node_map(self)
        
        # BFS from from_node to to_node
        from_node_obj, from_parent = node_map[from_node]
        to_node_obj, to_parent = node_map[to_node]
        
        # BFS to find path
        queue = [(from_node_obj, [from_node])]
        visited = {from_node}
        
        while queue:
            current, path = queue.pop(0)
            if current.label == to_node:
                return path
            
            # Go to children
            for child in current.children:
                if child.label not in visited:
                    visited.add(child.label)
                    queue.append((child, path + [child.label]))
            
            # Go to parent (if not root)
            if from_parent is not None and from_parent.label not in visited:
                visited.add(from_parent.label)
                queue.append((from_parent, path + [from_parent.label]))
        
        # Should never reach here
        raise ValueError("No path found")