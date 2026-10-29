"""Metered wrappers for network and file I/O."""

import io


class MeteredSocket:
    """A wrapper for socket-like objects that tracks I/O statistics."""
    
    def __init__(self, sock):
        self._sock = sock
        self.recv_ops = 0
        self.recv_bytes = 0
        self.send_ops = 0
        self.send_bytes = 0
    
    def recv(self, bufsize, flags=0):
        """Receive data from the socket."""
        self.recv_ops += 1
        data = self._sock.recv(bufsize, flags)
        self.recv_bytes += len(data)
        return data
    
    def send(self, data, flags=0):
        """Send data to the socket."""
        self.send_ops += 1
        sent = self._sock.send(data, flags)
        self.send_bytes += sent
        return sent
    
    def __enter__(self):
        """Context manager entry - doesn't call wrapped socket's __enter__."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - calls wrapped socket's __exit__."""
        return self._sock.__exit__(exc_type, exc_val, exc_tb)


class MeteredFile:
    """A wrapper for file-like objects that tracks I/O statistics."""
    
    def __init__(self, file=None):
        """Initialize with optional file, creates BytesIO if not provided."""
        if file is None:
            self._file = io.BytesIO()
        else:
            self._file = file
        self.read_ops = 0
        self.read_bytes = 0
        self.write_ops = 0
        self.write_bytes = 0
    
    def read(self, size=-1):
        """Read data from the file."""
        self.read_ops += 1
        data = self._file.read(size)
        self.read_bytes += len(data)
        return data
    
    def write(self, data):
        """Write data to the file."""
        self.write_ops += 1
        written = self._file.write(data)
        self.write_bytes += written
        return written
    
    def __enter__(self):
        """Context manager entry - doesn't call wrapped file's __enter__."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - doesn't call wrapped file's __exit__."""
        return False