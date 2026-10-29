from dataclasses import dataclass
from typing import Optional, List, Any


@dataclass
class Zipper:
    """A zipper for navigating a binary tree."""
    path: List[dict]  # Path from root to parent of focus
    value: Any
    left: Optional[dict]
    right: Optional[dict]
    
    @staticmethod
    def from_tree(tree: dict) -> 'Zipper':
        """Create a zipper from a tree, with focus on the root."""
        return Zipper(
            path=[],
            value=tree["value"],
            left=tree.get("left"),
            right=tree.get("right")
        )
    
    def to_tree(self) -> dict:
        """Convert the zipper back to a tree."""
        if not self.path:
            return {
                "value": self.value,
                "left": self.left,
                "right": self.right
            }
        
        # Navigate up the path to the root
        current = self
        for i in range(len(self.path) - 1, -1, -1):
            parent = self.path[i]
            if parent["left"] is current:
                parent["left"] = current.value
                current.left = current.left
                current.right = current.right
            else:
                parent["right"] = current.value
                current.left = current.left
                current.right = current.right
            current = parent
        
        return self.path[0]
    
    def value(self) -> Any:
        """Get the value of the focus node."""
        return self.value
    
    def left(self) -> Optional['Zipper']:
        """Move focus to the left child."""
        if self.left is None:
            return None
        return Zipper(
            path=[{"left": self.left, "right": self.right}] + self.path,
            value=self.left["value"],
            left=self.left.get("left"),
            right=self.left.get("right")
        )
    
    def right(self) -> Optional['Zipper']:
        """Move focus to the right child."""
        if self.right is None:
            return None
        return Zipper(
            path=[{"left": self.left, "right": self.right}] + self.path,
            value=self.right["value"],
            left=self.right.get("left"),
            right=self.right.get("right")
        )
    
    def up(self) -> Optional['Zipper']:
        """Move focus to the parent."""
        if not self.path:
            return None
        parent = self.path[0]
        if parent["left"] is self:
            parent["left"] = self.left
            parent["right"] = self.right
        else:
            parent["right"] = self.left
            parent["left"] = self.right
        
        return Zipper(
            path=parent.get("path", []),
            value=parent["value"],
            left=parent.get("left"),
            right=parent.get("right")
        )
    
    def set_value(self, value: Any) -> 'Zipper':
        """Set the value of the focus node."""
        return Zipper(
            path=self.path,
            value=value,
            left=self.left,
            right=self.right
        )
    
    def set_left(self, subtree: dict) -> 'Zipper':
        """Set the left child of the focus node."""
        return Zipper(
            path=self.path,
            value=self.value,
            left=subtree,
            right=self.right
        )
    
    def set_right(self, subtree: dict) -> 'Zipper':
        """Set the right child of the focus node."""
        return Zipper(
            path=self.path,
            value=self.value,
            left=self.left,
            right=subtree
        )