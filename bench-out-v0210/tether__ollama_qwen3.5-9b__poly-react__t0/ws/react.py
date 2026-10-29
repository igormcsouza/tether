class InputCell:
    """A cell with a settable value."""
    
    def __init__(self, value):
        self.value = value


class ComputeCell:
    """A cell that computes its value from other cells."""
    
    def __init__(self, inputs, compute_fn):
        self.inputs = inputs
        self.compute_fn = compute_fn
        self._value = None
        self._callbacks = []
        self._compute()
    
    def _compute(self):
        """Compute the value based on current inputs."""
        inputs = [cell.value for cell in self.inputs]
        self._value = self.compute_fn(inputs)
        return self._value
    
    def add_callback(self, callback):
        """Add a callback that will be called when the value changes."""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback):
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def _notify_callbacks(self, new_value):
        """Notify all callbacks of the new value."""
        for callback in self._callbacks:
            callback(self, new_value)
    
    def _propagate(self):
        """Propagate changes through the dependency graph."""
        changed = True
        while changed:
            changed = False
            for cell in self.inputs:
                if isinstance(cell, ComputeCell):
                    # Recompute this cell
                    old_value = cell._value
                    cell._compute()
                    if cell._value != old_value:
                        changed = True
                        cell._notify_callbacks(cell._value)
    
    @property
    def value(self):
        """Get the current value."""
        return self._value
    
    @value.setter
    def value(self, new_value):
        """Set the value and propagate changes."""
        old_value = self._value
        self._value = new_value
        self._propagate()
    
    def __repr__(self):
        return f"ComputeCell({self.inputs}, {self.compute_fn})"