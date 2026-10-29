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
        """Find a node by label, returns (node, parent) or None if not found."""
        if self.label == label:
            return (self, None)
        for child in self.children:
            result = child._find_node(label)
            if result:
                return result
        return None

    def from_pov(self, from_node):
        """Reorient the tree so that from_node becomes the root."""
        # Find the node
        node, parent = self._find_node(from_node)
        if node is None:
            raise ValueError("Tree could not be reoriented")
        
        # If it's a singleton tree, return as is
        if parent is None and len(self.children) == 0:
            return node
        
        # If the node is the current root
        if parent is None:
            return node
        
        # Create the new root (the node we're reorienting to)
        new_root = Tree(from_node, list(node.children))
        
        # The former parent becomes a child of the new root
        # But we need to remove the node from parent's children first
        # and add parent as a child of new_root
        
        # Create a new parent node without the node as a child
        new_parent_children = [c for c in parent.children if c.label != from_node]
        new_parent = Tree(parent.label, new_parent_children)
        
        # Add the new parent as a child of the new root
        new_root.children.append(new_parent)
        
        # Now we need to handle the siblings of the node (children of parent)
        # They should become children of the new root
        # But wait, looking at the test cases more carefully...
        
        # Actually, looking at test "test_moves_children_of_the_new_root_to_same_level_as_former_parent":
        # tree = Tree("parent", [Tree("x", [Tree("kid-0"), Tree("kid-1")])])
        # expected = Tree("x", [Tree("kid-0"), Tree("kid-1"), Tree("parent")])
        # So the children of x stay as children, and parent becomes a child of x
        
        # And test "test_can_reroot_a_tree_with_a_parent_and_many_siblings":
        # tree = Tree("parent", [Tree("a"), Tree("x"), Tree("b"), Tree("c")])
        # expected = Tree("x", [Tree("parent", [Tree("a"), Tree("b"), Tree("c")])])
        # So parent becomes a child of x, and a, b, c become children of parent
        
        # So the logic is:
        # 1. The node becomes the new root
        # 2. The node's original children remain children of the new root
        # 3. The node's former parent becomes a child of the new root
        # 4. The former parent's other children (siblings of the node) become children of the former parent
        
        # Wait, but in the first case, parent has no other children, so it just becomes a child of x
        # In the second case, parent has a, b, c as children, so they become children of parent
        
        # Let me re-read the test cases...
        
        # Actually I think I need to rebuild the tree properly.
        # Let me think about this differently.
        
        # The tree structure is:
        # - from_node is somewhere in the tree
        # - We want from_node to be the root
        # - The parent of from_node becomes a child of from_node
        # - The children of from_node remain children of from_node
        # - The siblings of from_node (children of parent) become children of parent (which is now a child of from_node)
        
        # So the new structure is:
        # from_node
        #   - original children of from_node
        #   - parent (without from_node as child)
        #     - siblings of from_node
        
        # Let me implement this properly
        
        # First, find the node and its parent
        node, parent = self._find_node(from_node)
        if node is None:
            raise ValueError("Tree could not be reoriented")
        
        # If the node is the root, return as is
        if parent is None:
            return node
        
        # Create new root with original children
        new_root = Tree(from_node, list(node.children))
        
        # Create new parent without the node as a child
        new_parent_children = [c for c in parent.children if c.label != from_node]
        new_parent = Tree(parent.label, new_parent_children)
        
        # Add siblings (children of parent) as children of new parent
        # They are already in new_parent_children, so new_parent is correct
        
        # Add new parent as a child of new root
        new_root.children.append(new_parent)
        
        # Sort children by label for consistent output
        new_root.children.sort(key=lambda c: c.label)
        new_parent.children.sort(key=lambda c: c.label)
        
        return new_root

    def path_to(self, from_node, to_node):
        """Find the path between two nodes."""
        # Find both nodes
        from_node_obj, from_parent = self._find_node(from_node)
        to_node_obj, to_parent = self._find_node(to_node)
        
        if from_node_obj is None:
            raise ValueError("Tree could not be reoriented")
        if to_node_obj is None:
            raise ValueError("No path found")
        
        # BFS to find the path
        # We need to find the path from from_node to to_node
        # Since it's a tree, there's exactly one path
        
        # Build a graph representation for traversal
        # We need to traverse up and down
        
        # Let's do a BFS from from_node to find to_node
        # We need to track parent pointers to reconstruct the path
        
        # First, let's build an adjacency list
        # But we need to handle the tree structure properly
        
        # Actually, let's think about this differently.
        # In a tree, the path between two nodes goes through their lowest common ancestor.
        # We can find the path by:
        # 1. Finding the path from from_node to root
        # 2. Finding the path from to_node to root
        # 3. Finding the LCA and combining the paths
        
        # But actually, we can just do a BFS/DFS from from_node to find to_node
        
        # Let's build a graph where each node points to its neighbors
        # Then do BFS
        
        # Actually, let's just do a simple DFS/BFS
        
        # Build adjacency list
        adj = {}
        
        def build_adj(node):
            if node.label not in adj:
                adj[node.label] = []
            for child in node.children:
                adj[node.label].append(child.label)
                adj[child.label].append(node.label)
                build_adj(child)
        
        build_adj(from_node_obj)
        
        # BFS from from_node to to_node
        queue = [(from_node_obj, [from_node_obj.label])]
        visited = {from_node_obj.label}
        
        while queue:
            current, path = queue.pop(0)
            if current.label == to_node:
                return path
            for neighbor in adj[current.label]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((next(n for n in adj[neighbor] if n != current.label), path + [neighbor]))
        
        # This approach is getting complicated. Let me simplify.
        
        # Actually, let me just do a proper BFS
        # We need to find the path from from_node to to_node
        
        # Let's rebuild the adjacency properly
        adj = {}
        
        def build_adj_recursive(node):
            if node.label not in adj:
                adj[node.label] = []
            for child in node.children:
                adj[node.label].append(child.label)
                adj[child.label].append(node.label)
                build_adj_recursive(child)
        
        build_adj_recursive(from_node_obj)
        
        # BFS
        queue = [(from_node_obj, [from_node_obj.label])]
        visited = {from_node_obj.label}
        
        while queue:
            current, path = queue.pop(0)
            if current.label == to_node:
                return path
            for neighbor in adj[current.label]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    # Find the node with this label
                    neighbor_node = next(n for n in adj[neighbor] if neighbor in adj[n])
                    # Actually this is wrong. Let me fix.
                    queue.append((next(n for n in adj[neighbor] if n != current.label), path + [neighbor]))
        
        # Hmm, this is getting messy. Let me rewrite more carefully.
        
        # Actually, I realize the issue - I need to find the actual node object, not just the label
        # Let me rewrite this more carefully
        
        # Build adjacency list with node objects
        adj = {}
        
        def build_adj_recursive(node):
            if node.label not in adj:
                adj[node.label] = []
            for child in node.children:
                adj[node.label].append(child.label)
                adj[child.label].append(node.label)
                build_adj_recursive(child)
        
        build_adj_recursive(from_node_obj)
        
        # BFS to find path
        # We need to track which node object we're at
        # But we only have labels in adj
        
        # Let me use a different approach - find the path by going up to LCA and then down
        
        # Actually, let's just do a simple DFS that tracks the path
        
        # Find path from from_node to to_node
        # We'll do a DFS from from_node
        
        # First, let's find all nodes and build a proper graph
        all_nodes = []
        
        def collect_nodes(node):
            all_nodes.append(node)
            for child in node.children:
                collect_nodes(child)
        
        collect_nodes(from_node_obj)
        
        # Build adjacency
        adj = {node.label: [] for node in all_nodes}
        for node in all_nodes:
            for child in node.children:
                adj[node.label].append(child.label)
                adj[child.label].append(node.label)
        
        # BFS
        queue = [(from_node_obj, [from_node_obj.label])]
        visited = {from_node_obj.label}
        
        while queue:
            current_node, path = queue.pop(0)
            if current_node.label == to_node:
                return path
            for neighbor_label in adj[current_node.label]:
                if neighbor_label not in visited:
                    visited.add(neighbor_label)
                    # Find the neighbor node
                    neighbor_node = next(n for n in all_nodes if n.label == neighbor_label)
                    queue.append((neighbor_node, path + [neighbor_label]))
        
        return []  # Should never reach here


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
        """Find a node by label, returns (node, parent) or None if not found."""
        if self.label == label:
            return (self, None)
        for child in self.children:
            result = child._find_node(label)
            if result:
                return result
        return None

    def from_pov(self, from_node):
        """Reorient the tree so that from_node becomes the root."""
        # Find the node
        node, parent = self._find_node(from_node)
        if node is None:
            raise ValueError("Tree could not be reoriented")
        
        # If it's a singleton tree, return as is
        if parent is None and len(self.children) == 0:
            return node
        
        # If the node is the current root
        if parent is None:
            return node
        
        # Create the new root (the node we're reorienting to)
        new_root = Tree(from_node, list(node.children))
        
        # The former parent becomes a child of the new root
        # But we need to remove the node from parent's children first
        # and add parent as a child of new_root
        
        # Create a new parent node without the node as a child
        new_parent_children = [c for c in parent.children if c.label != from_node]
        new_parent = Tree(parent.label, new_parent_children)
        
        # Add the new parent as a child of the new root
        new_root.children.append(new_parent)
        
        # Sort children by label for consistent output
        new_root.children.sort(key=lambda c: c.label)
        new_parent.children.sort(key=lambda c: c.label)
        
        return new_root

    def path_to(self, from_node, to_node):
        """Find the path between two nodes."""
        # Find both nodes
        from_node_obj, from_parent = self._find_node(from_node)
        to_node_obj, to_parent = self._find_node(to_node)
        
        if from_node_obj is None:
            raise ValueError("Tree could not be reoriented")
        if to_node_obj is None:
            raise ValueError("No path found")
        
        # Build adjacency list
        all_nodes = []
        
        def collect_nodes(node):
            all_nodes.append(node)
            for child in node.children:
                collect_nodes(child)
        
        collect_nodes(from_node_obj)
        
        # Build adjacency
        adj = {node.label: [] for node in all_nodes}
        for node in all_nodes:
            for child in node.children:
                adj[node.label].append(child.label)
                adj[child.label].append(node.label)
        
        # BFS to find path
        queue = [(from_node_obj, [from_node_obj.label])]
        visited = {from_node_obj.label}
        
        while queue:
            current_node, path = queue.pop(0)
            if current_node.label == to_node:
                return path
            for neighbor_label in adj[current_node.label]:
                if neighbor_label not in visited:
                    visited.add(neighbor_label)
                    # Find the neighbor node
                    neighbor_node = next(n for n in all_nodes if n.label == neighbor_label)
                    queue.append((neighbor_node, path + [neighbor_label]))
        
        return []  # Should never reach here