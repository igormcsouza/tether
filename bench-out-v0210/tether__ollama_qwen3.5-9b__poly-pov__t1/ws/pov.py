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

    def __hash__(self):
        return hash(self.label)

    def __repr__(self):
        return f"Tree({self.label}, {self.children})"

    def from_pov(self, from_node):
        """Reparent the tree from the perspective of from_node."""
        # Find the node with the given label
        target = self._find_node(self, from_node)
        if target is None:
            raise ValueError("Tree could not be reoriented")
        
        # If the node is the same as self, return as is
        if target is self:
            return self
        
        # Create a new root with the target node's label and its original children
        new_root = Tree(target.label, list(target.children))
        
        # Find the parent of the target node
        parent = self._find_parent(self, target)
        
        if parent is not None:
            # Remove the target from parent's children
            parent.children = [c for c in parent.children if c is not target]
            
            # Add the old parent as a child of the new root
            new_root.children.append(parent)
        
        # Sort children by label
        new_root.children.sort(key=lambda c: c.label)
        
        return new_root

    def _find_node(self, tree, label):
        """Find a node with the given label in the tree."""
        if tree.label == label:
            return tree
        for child in tree.children:
            result = self._find_node(child, label)
            if result is not None:
                return result
        return None

    def _find_parent(self, tree, child):
        """Find the parent of a child node."""
        if tree.children and child in tree.children:
            return tree
        for child_tree in tree.children:
            result = self._find_parent(child_tree, child)
            if result is not None:
                return result
        return None

    def path_to(self, from_node, to_node):
        """Find the path between two nodes."""
        # Find both nodes
        from_node_obj = self._find_node(self, from_node)
        if from_node_obj is None:
            raise ValueError("Tree could not be reoriented")
        
        to_node_obj = self._find_node(self, to_node)
        if to_node_obj is None:
            raise ValueError("No path found")
        
        # Find the path using BFS from the start node
        path = self._find_path_from_node(self, from_node_obj, to_node_obj)
        return path

    def _find_path_from_node(self, tree, start, end):
        """Find path from start to end using BFS."""
        # BFS with parent tracking - we need to track parent pointers
        # Build a parent map first
        parent_map = {}
        queue = [tree]
        parent_map[tree] = None
        
        while queue:
            current = queue.pop(0)
            for child in current.children:
                if child not in parent_map:
                    parent_map[child] = current
                    queue.append(child)
        
        # Now find the path from start to end by backtracking through parents
        path = []
        current = end
        while current is not None:
            path.append(current.label)
            current = parent_map.get(current)
        
        path.reverse()
        return path

    def __eq__(self, other):
        if not isinstance(other, Tree):
            return False
        return self.__dict__() == other.__dict__()