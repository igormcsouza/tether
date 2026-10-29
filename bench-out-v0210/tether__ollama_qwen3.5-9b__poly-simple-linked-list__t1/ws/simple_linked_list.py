class EmptyListException(Exception):
    """Exception raised when the linked list is empty."""
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class Node:
    """A node in the linked list."""
    def __init__(self, value):
        self._value = value
        self._next = None
    
    def value(self):
        return self._value
    
    def next(self):
        return self._next


class LinkedList:
    """A singly linked list implementation."""
    
    def __init__(self, values=None):
        self._head = None
        self._tail = None
        self._size = 0
        if values:
            for value in values:
                self.push(value)
    
    def __len__(self):
        return self._size
    
    def head(self):
        if self._head is None:
            raise EmptyListException("The list is empty.")
        return self._head
    
    def push(self, value):
        """Add a value to the list (becomes the new head)."""
        new_node = Node(value)
        new_node._next = self._head
        self._head = new_node
        if self._tail is None:
            self._tail = new_node
        self._size += 1
    
    def pop(self):
        """Remove and return the head value from the list."""
        if self._head is None:
            raise EmptyListException("The list is empty.")
        
        value = self._head.value()
        self._head = self._head._next
        
        if self._head is None:
            self._tail = None
        
        self._size -= 1
        return value
    
    def reversed(self):
        """Return an iterator that yields values in reverse order."""
        return reversed_iter(self._head)
    
    def __iter__(self):
        """Return an iterator over the list values."""
        return iter_values(self._head)


def iter_values(head):
    """Generator that yields values from head to tail."""
    current = head
    while current is not None:
        yield current.value()
        current = current.next()


def reversed_iter(head):
    """Generator that yields values from tail to head."""
    values = []
    current = head
    while current is not None:
        values.append(current.value())
        current = current.next()
    for value in reversed(values):
        yield value