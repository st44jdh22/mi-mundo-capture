"""Private original-file interface and fsynced local synthetic implementation."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Protocol


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PrivateObjects(Protocol):
    """Production implementation must enforce private ACLs, versioning and restore.

    put must return only after durable storage and readback. Keys are opaque,
    never caller-controlled URLs. Implementations must not log document bytes.
    """
    def put(self, data: bytes) -> str: ...
    def get(self, key: str) -> bytes: ...


class LocalSyntheticObjects:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink():
            raise ValueError('Object root cannot be a symlink')
        os.chmod(self.root, 0o700)

    def _path(self, key):
        if not re.fullmatch(r'[a-f0-9]{64}', key):
            raise ValueError('Invalid object key')
        return self.root / key

    def put(self, data):
        # Fixed fixture signature prevents accidental use for real documents.
        if (not isinstance(data, bytes) or not data.startswith((b'SYNTHETIC\n', b'%PDF-1.4\n%SYNTHETIC\n'))
                or not 0 < len(data) <= 8 * 1024 * 1024):
            raise ValueError('Only bounded synthetic documents are permitted')
        key = digest(data)
        destination = self._path(key)
        if destination.exists() or destination.is_symlink():
            if self.get(key) != data:
                raise ValueError('Object conflict')
            return key
        fd, name = tempfile.mkstemp(dir=self.root, prefix='pending-')
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            # Atomic immutable creation. Never overwrite an existing object.
            try:
                os.link(name, destination)
            except FileExistsError:
                if self.get(key) != data:
                    raise ValueError('Object conflict')
            directory = os.open(self.root, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            os.unlink(name)
        if digest(self.get(key)) != key:
            raise IOError('Object readback mismatch')
        return key

    def get(self, key):
        fd = os.open(self._path(key), os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            data = stream.read(8 * 1024 * 1024 + 1)
        if digest(data) != key:
            raise IOError('Source object integrity failure')
        return data
