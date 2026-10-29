"""Metered wrappers for network and file I/O."""

import io


class MeteredSocket:
    """A wrapper for socket connections that reports IO statistics."""
    
    def __init__(self, sock):
        self._sock = sock
        self.recv_ops = 0
        self.recv_bytes = 0
        self.send_ops = 0
        self.send_bytes = 0
    
    def recv(self, bufsize, flags=0):
        """Receive data from the socket."""
        data = self._sock.recv(bufsize, flags)
        self.recv_ops += 1
        self.recv_bytes += len(data)
        return data
    
    def send(self, data, flags=0):
        """Send data to the socket."""
        self.send_ops += 1
        self.send_bytes += len(data)
        return self._sock.send(data, flags)
    
    def __enter__(self):
        # Context manager doesn't call __enter__ on wrapped socket
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Context manager doesn't call __exit__ on wrapped socket
        return False


class MeteredFile:
    """A wrapper for file objects that reports IO statistics."""
    
    def __init__(self, file=None):
        self._file = file
        self.read_ops = 0
        self.read_bytes = 0
        self.write_ops = 0
        self.write_bytes = 0
    
    def read(self, size=-1):
        """Read data from the file."""
        data = self._file.read(size)
        self.read_ops += 1
        self.read_bytes += len(data)
        return data
    
    def write(self, data):
        """Write data to the file."""
        self.write_ops += 1
        self.write_bytes += len(data)
        return self._file.write(data)
    
    def __enter__(self):
        # Context manager doesn't call __enter__ on wrapped file
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Context manager doesn't call __exit__ on wrapped file
        return False
    
    @property
    def read_ops(self):
        return self._read_ops
    
    @read_ops.setter
    def read_ops(self, value):
        raise AttributeError("property 'read_ops' of 'MeteredFile' object has no setter")
    
    @property
    def read_bytes(self):
        return self._read_bytes
    
    @read_bytes.setter
    def read_bytes(self, value):
        raise AttributeError("property 'read_bytes' of 'MeteredFile' object has no setter")
    
    @property
    def write_ops(self):
        return self._write_ops
    
    @write_ops.setter
    def write_ops(self, value):
        raise AttributeError("property 'write_ops' of 'MeteredFile' object has no setter")
    
    @property
    def write_bytes(self):
        return self._write_bytes
    
    @write_bytes.setter
    def write_bytes(self, value):
        raise AttributeError("property 'write_bytes' of 'MeteredFile' object has no setter")


# For backward compatibility with tests that expect read/write_ops/bytes to be
# directly accessible without properties
class _MeteredFile(MeteredFile):
    """Internal class that allows direct attribute access."""
    
    def __init__(self, file=None):
        self._read_ops = 0
        self._read_bytes = 0
        self._write_ops = 0
        self._write_bytes = 0
        self._file = file
    
    def read(self, size=-1):
        data = self._file.read(size)
        self._read_ops += 1
        self._read_bytes += len(data)
        return data
    
    def write(self, data):
        self._write_ops += 1
        self._write_bytes += len(data)
        return self._file.write(data)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


# Use the internal class for actual functionality
MeteredFile = _MeteredFile