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

    def _find_node(self, label):
        """Find a node by its label, returning the node or None."""
        if self.label == label:
            return self
        for child in self.children:
            result = child._find_node(label)
            if result:
                return result
        return None

    def _find_parent(self, label):
        """Find the parent of a node with the given label."""
        if self.label == label:
            return None
        for child in self.children:
            if child.label == label:
                return self
            result = child._find_parent(label)
            if result:
                return result
        return None

    def from_pov(self, from_node):
        """Reorient the tree from the perspective of from_node."""
        # Find the node
        target = self._find_node(from_node)
        if target is None:
            raise ValueError("Tree could not be reoriented")
        
        # If it's a singleton tree, return as is
        if len(self.children) == 0 and self.label == from_node:
            return self
        
        # If the target is the current root, return as is
        if self.label == from_node:
            return self
        
        # We need to reorient the tree so from_node becomes root
        # Find the parent of target
        parent = self._find_parent(from_node)
        
        if parent is None:
            # from_node is the root, return as is
            return self
        
        # Now we need to build the new tree
        # The new root is target
        # target's children remain children
        # parent becomes a child of target
        # parent's other children (siblings of target) become children of parent
        # But we also need to handle parent's parent, etc.
        
        # We need to recursively reorient the entire path from parent to root
        # Let's do this by building the new tree from the bottom up
        
        # First, let's find all ancestors of target (including parent)
        ancestors = []
        current = parent
        while current:
            ancestors.append(current)
            current = self._find_parent(current.label)
        
        # Now build the new tree
        # Start with target as root
        new_root = Tree(target.label, list(target.children))
        
        # For each ancestor (from parent to root), we need to:
        # 1. Create a new node for the ancestor
        # 2. Add the ancestor's other children (siblings of the previous ancestor) as children
        # 3. Add the reoriented previous ancestor as a child
        
        # Actually, let's think about this differently
        # We need to traverse from target up to root, and for each step:
        # - The current node becomes a child of the previous node (which is closer to root)
        # - The current node's other children (siblings) become children of the current node
        
        # Let's do this bottom-up
        # Start with target's siblings (children of parent, excluding target)
        # These become children of parent
        # Then parent becomes a child of target
        
        # But we also need to handle parent's siblings, etc.
        
        # Let's build the new tree by traversing from target up to root
        # and collecting all the nodes and their children
        
        # First, let's find all nodes on the path from target to root
        path_nodes = []
        current = target
        while current:
            path_nodes.append(current)
            parent = self._find_parent(current.label)
            if parent:
                current = parent
            else:
                break
        
        # Now we need to build the new tree
        # The new root is target
        # target's children stay as children
        # target's parent becomes a child of target
        # target's parent's other children (siblings of target) become children of target's parent
        # target's parent's parent becomes a child of target's parent
        # etc.
        
        # Let's build this recursively
        return self._build_new_tree(target, self._find_parent(target.label))

    def _build_new_tree(self, target, parent):
        """Build the new tree with target as root."""
        # Create the new root with target's original children
        new_root = Tree(target.label, list(target.children))
        
        if parent is None:
            return new_root
        
        # Reorient the parent and add it as a child of new_root
        reoriented_parent = self._reorient_parent_node(parent, target)
        new_root.children.append(reoriented_parent)
        
        return new_root

    def _reorient_parent_node(self, parent, excluded_child):
        """Reorient a parent node, excluding one child (the one that becomes parent of this)."""
        # Find all children of parent except excluded_child
        siblings = []
        for child in parent.children:
            if child.label != excluded_child.label:
                siblings.append(child)
        
        # Create new parent with siblings as children
        new_parent = Tree(parent.label, sorted(siblings))
        
        # Now we need to reorient the parent's parent
        parent_of_parent = self._find_parent(parent.label)
        
        if parent_of_parent is None:
            return new_parent
        
        # We need to recursively reorient the parent's parent
        # But we need to pass the excluded child (which is the parent itself)
        # Actually, we need to think about this differently
        
        # When we reorient parent_of_parent, we need to exclude parent
        # But parent_of_parent's children include parent and parent's siblings
        # We want to keep parent's siblings as children of parent_of_parent
        # But parent becomes a child of the new root (target)
        
        # So we need to recursively reorient parent_of_parent, excluding parent
        reoriented_parent_of_parent = self._reorient_parent_node_recursive(parent_of_parent, parent)
        
        # Add the reoriented parent_of_parent as a child of new_parent
        new_parent.children.append(reoriented_parent_of_parent)
        
        return new_parent

    def _reorient_parent_node_recursive(self, parent, excluded_child):
        """Recursively reorient a parent node."""
        # Find all children of parent except excluded_child
        siblings = []
        for child in parent.children:
            if child.label != excluded_child.label:
                siblings.append(child)
        
        # Create new parent with siblings as children
        new_parent = Tree(parent.label, sorted(siblings))
        
        # Now we need to reorient the parent's parent
        parent_of_parent = self._find_parent(parent.label)
        
        if parent_of_parent is None:
            return new_parent
        
        # Recursively reorient the parent's parent
        reoriented_parent_of_parent = self._reorient_parent_node_recursive(parent_of_parent, parent)
        
        # Add the reoriented parent_of_parent as a child of new_parent
        new_parent.children.append(reoriented_parent_of_parent)
        
        return new_parent

    def path_to(self, from_node, to_node):
        """Find the path from from_node to to_node."""
        # Find both nodes
        start = self._find_node(from_node)
        end = self._find_node(to_node)
        
        if start is None:
            raise ValueError("Tree could not be reoriented")
        if end is None:
            raise ValueError("No path found")
        
        # Find the path using BFS
        return self._find_path(start, end)

    def _find_path(self, start, end):
        """Find the path between two nodes using BFS with parent tracking."""
        if start.label == end.label:
            return [start.label]
        
        # BFS to find the path
        # We need to track both the node and the path taken to reach it
        queue = [(start, [start.label])]
        visited = {start.label}
        
        while queue:
            current, path = queue.pop(0)
            
            # Check children
            for child in current.children:
                if child.label == end.label:
                    return path + [child.label]
                if child.label not in visited:
                    visited.add(child.label)
                    queue.append((child, path + [child.label]))
            
            # Check parent
            parent = self._find_parent(current.label)
            if parent and parent.label not in visited:
                visited.add(parent.label)
                queue.append((parent, path + [parent.label]))
                # Check if parent is the target
                if parent.label == end.label:
                    return path + [parent.label]
        
        # If we get here, no path found (shouldn't happen in a tree)
        raise ValueError("No path found")