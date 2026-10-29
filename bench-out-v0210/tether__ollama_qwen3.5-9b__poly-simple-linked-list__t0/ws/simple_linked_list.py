class EmptyListException(Exception):
    """Exception raised when the linked list is empty."""
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class Node:
    """A node in the singly linked list."""
    def __init__(self, value):
        self._value = value
        self._next = None
    
    def value(self):
        return self._value
    
    def next(self):
        return self._next


class LinkedList:
    """A singly linked list implemented as a stack (LIFO)."""
    
    def __init__(self, values=None):
        self._head = None
        self._size = 0
        if values:
            for value in values:
                self.push(value)
    
    def head(self):
        """Return the head node of the list."""
        if self._head is None:
            raise EmptyListException("The list is empty.")
        return self._head
    
    def push(self, value):
        """Add a value to the head of the list."""
        new_node = Node(value)
        new_node._next = self._head
        self._head = new_node
        self._size += 1
    
    def pop(self):
        """Remove and return the value at the head of the list."""
        if self._head is None:
            raise EmptyListException("The list is empty.")
        value = self._head._value
        self._head = self._head._next
        self._size -= 1
        return value
    
    def __len__(self):
        """Return the number of elements in the list."""
        return self._size
    
    def __iter__(self):
        """Return an iterator over the list elements (from head to tail)."""
        current = self._head
        while current is not None:
            yield current.value()
            current = current.next()
    
    def reversed(self):
        """Return a new list with elements in reverse order."""
        reversed_list = LinkedList()
        for value in self:
            reversed_list.push(value)
        return reversed_list