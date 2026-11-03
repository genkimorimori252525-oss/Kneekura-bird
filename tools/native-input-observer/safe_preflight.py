"""Path checks for an isolated experiment; not an OS sandbox or race-proof guarantee."""
import hashlib
import os
from pathlib import Path
import re
import stat


def check_no_symlink(path, *, must_exist=True):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('absolute path without parent traversal required')
    current = Path(path.anchor)
    missing = False
    for part in path.parts[1:]:
        current = current / part
        if missing:
            continue
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            missing = True
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f'symlink not permitted: {current}')
    if missing and must_exist:
        raise FileNotFoundError(path)
    if not missing and os.path.realpath(path) != str(path):
        raise ValueError('canonical path mismatch')
    return path


def check_regular_file(path, expected_sha256):
    if not isinstance(expected_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise ValueError('expected SHA-256 must be 64 lowercase hex characters')
    path = check_no_symlink(path)
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('input must be a regular non-hardlinked file')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags)
    try:
        actual = os.fstat(fd)
        if not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1 or (actual.st_dev, actual.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError('input changed during open')
        digest = hashlib.sha256()
        with os.fdopen(fd, 'rb', closefd=False) as data:
            for block in iter(lambda: data.read(1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != expected_sha256:
            raise ValueError(f'input hash mismatch: {path}')
    finally:
        os.close(fd)
    return path


def create_private_scratch(path):
    path = check_no_symlink(path, must_exist=False)
    check_no_symlink(path.parent)
    os.mkdir(path, 0o700)
    if stat.S_IMODE(os.lstat(path).st_mode) != 0o700:
        raise ValueError('scratch directory is not mode 0700; preserve for inspection')
    return path
