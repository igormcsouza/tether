import socket
import os


class MeteredSocket(socket.socket):
    """A socket wrapper that tracks read/write statistics."""
    
    def __init__(self, sock=None):
        if sock is None:
            sock = socket.socket()
        self._sock = sock
        self._recv_bytes = 0
        self._recv_ops = 0
        self._send_bytes = 0
        self._send_ops = 0
    
    @property
    def recv_bytes(self):
        return self._recv_bytes
    
    @property
    def recv_ops(self):
        return self._recv_ops
    
    @property
    def send_bytes(self):
        return self._send_bytes
    
    @property
    def send_ops(self):
        return self._send_ops
    
    def recv(self, bufsize, flags=0):
        data = self._sock.recv(bufsize, flags)
        self._recv_bytes += len(data)
        self._recv_ops += 1
        return data
    
    def send(self, data, flags=0):
        sent = self._sock.send(data, flags)
        self._send_bytes += sent
        self._send_ops += 1
        return sent
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._sock.__exit__(exc_type, exc_val, exc_tb)


class MeteredFile:
    """A file wrapper that tracks read/write statistics."""
    
    def __init__(self, file=None):
        if file is None:
            file = open(os.devnull, 'r+b')
        self._file = file
        self._read_bytes = 0
        self._read_ops = 0
        self._write_bytes = 0
        self._write_ops = 0
    
    @property
    def read_bytes(self):
        return self._read_bytes
    
    @property
    def read_ops(self):
        return self._read_ops
    
    @property
    def write_bytes(self):
        return self._write_bytes
    
    @property
    def write_ops(self):
        return self._write_ops
    
    def read(self, size=-1):
        data = self._file.read(size)
        self._read_bytes += len(data)
        self._read_ops += 1
        return data
    
    def write(self, data):
        written = self._file.write(data)
        self._write_bytes += written
        self._write_ops += 1
        return written
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._file.__exit__(exc_type, exc_val, exc_tb)