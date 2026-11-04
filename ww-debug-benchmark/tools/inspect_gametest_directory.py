#!/usr/bin/env python3
"""Observe a fixed GameTest run path without authorizing or starting a run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys

MAX_PROPERTIES_BYTES = 1024 * 1024


class Rejected(Exception):
    pass


class Unavailable(Exception):
    pass


def identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid


def describe(value: os.stat_result) -> dict[str, int]:
    return {"device": value.st_dev, "inode": value.st_ino, "owner_uid": value.st_uid,
            "owner_gid": value.st_gid, "mode": stat.S_IMODE(value.st_mode)}


def normalized_absolute(path: str) -> bool:
    return (bool(path) and path.startswith("/") and not path.startswith("//")
            and path != "/" and "\x00" not in path and os.path.normpath(path) == path)


def metadata_signature(value: os.stat_result) -> tuple[int, ...]:
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_uid, value.st_gid, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def open_pinned_for_read(descriptor: int) -> int:
    return os.open(f"/proc/self/fd/{descriptor}", os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)


def inspect(workspace: str, project: str, expected: str) -> dict:
    """Return an observation only; no receipt, exclusive access, or run safety is inferred."""
    if (not sys.platform.startswith("linux") or not all(hasattr(os, name) for name in
            ("O_PATH", "O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK"))
            or os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd
            or os.stat not in os.supports_follow_symlinks or os.listdir not in os.supports_fd):
        raise Unavailable("NO_REQUIRED_LINUX_NOFOLLOW_SUPPORT")
    if (not normalized_absolute(workspace) or not normalized_absolute(project)
            or not project.startswith(workspace + "/")
            or os.path.basename(project) != "ww-debug-benchmark"):
        raise Rejected("INVALID_OR_AMBIGUOUS_PATH")
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise Rejected("INVALID_EXPECTED_SHA256")
    opened: list[int] = []
    chain: list[tuple[int, str, int, tuple[int, int, int, int, int]]] = []
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC

    def directory(parent: int, name: str) -> int:
        try:
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise Rejected("DIRECTORY_MISSING") from exc
        if stat.S_ISLNK(before.st_mode):
            raise Rejected("SYMLINK_COMPONENT")
        if not stat.S_ISDIR(before.st_mode):
            raise Rejected("NON_DIRECTORY_COMPONENT")
        child = os.open(name, dir_flags, dir_fd=parent)
        opened.append(child)
        actual = os.fstat(child)
        after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if identity(before) != identity(actual) or identity(actual) != identity(after):
            raise Unavailable("DIRECTORY_CHANGED_DURING_INSPECTION")
        chain.append((parent, name, child, identity(actual)))
        return child

    try:
        root = os.open("/", dir_flags)
        opened.append(root)
        current = root
        workspace_parts = workspace.strip("/").split("/")
        for part in workspace_parts:
            current = directory(current, part)
        workspace_fd = current
        for part in project[len(workspace) + 1:].split("/"):
            current = directory(current, part)
        project_fd = current
        result = {"scope": "observation_only", "workspace_identity": describe(os.fstat(workspace_fd)),
                  "project_identity": describe(os.fstat(project_fd)), "run_identity": None}

        try:
            run_stat = os.stat("run-gametest", dir_fd=project_fd, follow_symlinks=False)
        except FileNotFoundError:
            run_stat = None

        if run_stat is None:
            result["observation"] = "ABSENT"
        else:
            run_fd = directory(project_fd, "run-gametest")
            if identity(run_stat) != identity(os.fstat(run_fd)):
                raise Unavailable("DIRECTORY_CHANGED_DURING_INSPECTION")
            result["run_identity"] = describe(os.fstat(run_fd))
            names = os.listdir(run_fd)
            if not names:
                result["observation"] = "EMPTY"
            elif len(names) != 1 or names[0] != "server.properties":
                raise Rejected("UNEXPECTED_RUN_CONTENT")
            else:
                first = os.stat("server.properties", dir_fd=run_fd, follow_symlinks=False)
                if not stat.S_ISREG(first.st_mode) or first.st_nlink != 1:
                    raise Rejected("PROPERTIES_NOT_EXCLUSIVE_REGULAR_FILE")
                if first.st_size > MAX_PROPERTIES_BYTES:
                    raise Rejected("PROPERTIES_TOO_LARGE")
                pinned = os.open("server.properties", os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 dir_fd=run_fd)
                opened.append(pinned)
                pinned_stat = os.fstat(pinned)
                if metadata_signature(first) != metadata_signature(pinned_stat):
                    raise Unavailable("PROPERTIES_CHANGED_DURING_INSPECTION")
                if not stat.S_ISREG(pinned_stat.st_mode) or pinned_stat.st_nlink != 1:
                    raise Rejected("PROPERTIES_NOT_EXCLUSIVE_REGULAR_FILE")
                # procfs reopens the pinned inode rather than resolving the mutable project path.
                read_fd = open_pinned_for_read(pinned)
                opened.append(read_fd)
                if metadata_signature(os.fstat(read_fd)) != metadata_signature(pinned_stat):
                    raise Unavailable("PROPERTIES_CHANGED_DURING_INSPECTION")
                digest = hashlib.sha256()
                total = 0
                while True:
                    block = os.read(read_fd, 65536)
                    if not block:
                        break
                    total += len(block)
                    if total > MAX_PROPERTIES_BYTES:
                        raise Rejected("PROPERTIES_TOO_LARGE")
                    digest.update(block)
                after = os.stat("server.properties", dir_fd=run_fd, follow_symlinks=False)
                if (metadata_signature(after) != metadata_signature(pinned_stat)
                        or metadata_signature(os.fstat(read_fd)) != metadata_signature(pinned_stat)):
                    raise Unavailable("PROPERTIES_CHANGED_DURING_INSPECTION")
                if digest.hexdigest() != expected:
                    raise Rejected("PROPERTIES_HASH_MISMATCH")
                result["observation"] = "MATCHING_PROPERTIES_ONLY"
                result["properties_sha256"] = digest.hexdigest()

            if os.listdir(run_fd) != names:
                raise Unavailable("RUN_CONTENT_CHANGED_DURING_INSPECTION")

        for parent, name, child, captured in chain:
            current_stat = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if identity(os.fstat(child)) != captured or identity(current_stat) != captured:
                raise Unavailable("DIRECTORY_CHANGED_DURING_INSPECTION")
        if run_stat is None:
            try:
                os.stat("run-gametest", dir_fd=project_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise Unavailable("RUN_PATH_CHANGED_DURING_INSPECTION")
        return result
    except (Rejected, Unavailable):
        raise
    except (OSError, ValueError, TypeError) as exc:
        # Do not expose raw paths or infer safety from an unreadable/racing filesystem.
        raise Unavailable("FILESYSTEM_INSPECTION_FAILED") from exc
    finally:
        close_failed = False
        for descriptor in reversed(opened):
            try:
                os.close(descriptor)
            except OSError:
                close_failed = True
        if close_failed:
            raise Unavailable("DESCRIPTOR_CLOSE_FAILED")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--expected-properties-sha256", required=True)
    args = parser.parse_args()
    try:
        result = inspect(args.workspace_root, args.project_dir, args.expected_properties_sha256)
        status = 0
    except Rejected as exc:
        result = {"scope": "observation_only", "observation": "REJECTED", "reason": str(exc)}
        status = 1
    except Unavailable as exc:
        result = {"scope": "observation_only", "observation": "UNAVAILABLE", "reason": str(exc)}
        status = 2
    print(json.dumps(result, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
