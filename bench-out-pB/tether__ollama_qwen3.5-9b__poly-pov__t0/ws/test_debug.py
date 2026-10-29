from pov import Tree

tree = Tree("parent", [Tree("a"), Tree("x"), Tree("b"), Tree("c")])
print("Original tree:", tree.__dict__())

# Debug _find_node
result = tree._find_node("x")
print("Find result:", result)
if result:
    node, parent = result
    print("Node label:", node.label, "Parent:", parent)
    print("Node children:", node.children)
