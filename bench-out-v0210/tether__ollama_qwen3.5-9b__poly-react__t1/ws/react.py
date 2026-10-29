class InputCell:
    """A cell with a settable value."""
    
    def __init__(self, value):
        self._value = value
    
    @property
    def value(self):
        return self._value
    
    @value.setter
    def value(self, new_value):
        self._value = new_value


class ComputeCell:
    """A cell that computes its value from other cells."""
    
    def __init__(self, inputs, compute_func):
        self.inputs = inputs
        self.compute_func = compute_func
        self._value = None
        self._callbacks = []
        self._compute()
    
    def _compute(self):
        """Compute the value based on inputs."""
        inputs_values = [input_cell.value for input_cell in self.inputs]
        self._value = self.compute_func(inputs_values)
        return self._value
    
    def add_callback(self, callback):
        """Add a callback to be called when the value changes."""
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
                    old_value = cell._value
                    cell._compute()
                    if cell._value != old_value:
                        changed = True
                        cell._propagate()
    
    def _update_value(self):
        """Update the cell's value and notify callbacks if changed."""
        old_value = self._value
        self._compute()
        new_value = self._value
        
        # Only notify if value actually changed
        if new_value != old_value:
            self._notify_callbacks(new_value)
            return True
        return False
    
    @property
    def value(self):
        return self._value
    
    @value.setter
    def value(self, new_value):
        self._value = new_value