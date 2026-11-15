"""See what a command changed by comparing the workspace files before and after it (H2).

The harness used to guess from the command text which files a command wrote. A `Tracker` looks
at the files instead: `scan()` takes the first look, each `step()` reports what differs from
the look before. Pure stdlib, no threads.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import NamedTuple

from tether.sandbox import _MASKED_NAME_RE

# ponytail: ceilings, not tuned values. A repo with more files than MAX_ENTRIES disables the
# tracker and the harness falls back to reading the command text; the cache keeps at most
# MAX_CACHE_BYTES of old bytes, first come, so a huge tree cannot eat the memory.
MAX_ENTRIES = 50_000
MAX_FILE_BYTES = 256_000
MAX_CACHE_BYTES = 32_000_000
SKIP_DIRS = frozenset({".git", ".venv", "node_modules", "__pycache__", ".tether"})

Meta = dict[str, tuple[int, int]]  # rel path -> (mtime_ns, size)
Sig = tuple[int, int, int]  # (mtime_ns, size, inode): `mv a b` keeps a's mtime, not its inode


class Changes(NamedTuple):
    created: list[str]
    modified: list[str]
    deleted: list[str]
    touched: list[str]  # rewritten with the same bytes


class Tracker:
    def __init__(self, root: str | os.PathLike[str], ignore: str = "") -> None:
        self.root = Path(root).resolve()
        # absolute path prefix of the store's database: its -wal/-shm files change on every turn
        self.ignore = ignore
        self.disabled = False
        self._meta: dict[str, Sig] = {}
        self._cache: dict[str, bytes] = {}
        self._cache_bytes = 0
        self._old: dict[str, bytes | None] = {}

    def _walk(self) -> dict[str, Sig] | None:
        """Files under the root, or None when there are more than MAX_ENTRIES."""
        meta: dict[str, Sig] = {}
        base = str(self.root)
        for dirpath, dirnames, filenames in os.walk(base):
            # hidden directories hold tool state, not the project
            dirnames[:] = sorted(
                d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
            )
            for name in sorted(filenames):
                if _MASKED_NAME_RE.match(name):
                    continue  # secrets are never read, cached or snapshotted (Rule 6)
                full = os.path.join(dirpath, name)
                if self.ignore and full.startswith(self.ignore):
                    continue
                try:
                    st = os.stat(full)
                except OSError:
                    continue  # gone between listing and stat
                if not stat.S_ISREG(st.st_mode):
                    continue
                meta[os.path.relpath(full, base)] = (st.st_mtime_ns, st.st_size, st.st_ino)
                if len(meta) > MAX_ENTRIES:
                    return None
        return meta

    def _read(self, rel: str, size: int) -> bytes | None:
        if size > MAX_FILE_BYTES:
            return None
        try:
            return (self.root / rel).read_bytes()
        except OSError:
            return None

    def _keep(self, rel: str, data: bytes | None) -> None:
        """Cache `data` for `rel` if it fits the budget; drop what was cached before."""
        self._cache_bytes -= len(self._cache.pop(rel, b""))
        if data is not None and self._cache_bytes + len(data) <= MAX_CACHE_BYTES:
            self._cache[rel] = data
            self._cache_bytes += len(data)

    def scan(self) -> Meta:
        """First look at the workspace; an oversized tree disables the tracker."""
        meta = self._walk()
        if meta is None:
            self.disabled = True
            return {}
        self._meta = meta
        for rel, (_, size, _) in meta.items():
            self._keep(rel, self._read(rel, size))
        return {rel: (sig[0], sig[1]) for rel, sig in meta.items()}

    def step(self) -> Changes:
        """What differs from the previous look; the new files become the baseline."""
        self._old = {}
        if self.disabled:
            return Changes([], [], [], [])
        new = self._walk()
        if new is None:
            self.disabled = True
            return Changes([], [], [], [])
        created: list[str] = []
        modified: list[str] = []
        touched: list[str] = []
        for rel, sig in new.items():
            seen = self._meta.get(rel)
            if seen == sig:
                continue
            data = self._read(rel, sig[1])
            old = self._cache.get(rel)
            if seen is None:
                created.append(rel)
                self._old[rel] = None
            elif old is not None and old == data:
                touched.append(rel)
            else:
                modified.append(rel)
                self._old[rel] = old
            self._keep(rel, data)
        deleted = sorted(set(self._meta) - set(new))
        for rel in deleted:
            self._old[rel] = self._cache.get(rel)
            self._keep(rel, None)
        self._meta = new
        return Changes(created, modified, deleted, touched)

    def refresh(self, rels: list[str]) -> None:
        """Take the current state of `rels` as the baseline: the harness wrote them itself."""
        for rel in rels:
            try:
                st = os.stat(self.root / rel)
            except OSError:
                self._meta.pop(rel, None)
                self._keep(rel, None)
                continue
            self._meta[rel] = (st.st_mtime_ns, st.st_size, st.st_ino)
            self._keep(rel, self._read(rel, st.st_size))

    def old(self, rel: str) -> bytes | None:
        """Bytes of `rel` before the last step; None when unknown or the file was created."""
        return self._old.get(rel)
