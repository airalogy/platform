"""Owner-only POSIX credential storage. Windows ACL enrollment is not certified."""

import json
import os
import re
import stat
from pathlib import Path


def _parent(path: Path):
    if os.name != "posix":
        raise ValueError(
            "Pairing credential files require POSIX permissions; Windows ACL support is pending"
        )
    parent = path.parent
    info = parent.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError(
            "Credential parent must be an owner-only directory (mode 0700), not a symlink"
        )
    fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    opened = os.fstat(fd)
    if (
        (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)
        or opened.st_uid != os.getuid()
        or opened.st_mode & 0o077
    ):
        os.close(fd)
        raise ValueError("Credential directory changed while opening")
    return fd


def write_credentials(path: Path, content: dict) -> None:
    """Exclusive creation before network claim; never replace an existing identity."""
    parent_fd = _parent(path)
    try:
        fd = os.open(
            path.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent_fd,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            json.dump(content, target, ensure_ascii=True)
            target.flush()
            os.fsync(target.fileno())
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def read_private_json(path: Path) -> dict:
    parent_fd = _parent(path)
    try:
        fd = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd
        )
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or info.st_nlink != 1
                or info.st_size > 16384
            ):
                raise ValueError(
                    "Credential file must be a small owner-only regular file, without hard links"
                )
            content = json.loads(source.read(16385))
    finally:
        os.close(parent_fd)
    if not isinstance(content, dict):
        raise ValueError("Private credential document must be an object")  # noqa: TRY004 - consistent credential validation boundary
    return content


def read_credentials(path: Path) -> dict:
    content = read_private_json(path)
    if (
        not isinstance(content, dict)
        or content.get("schema") != "airalogy.gateway-credential.v1"
        or not re.fullmatch(r"aigw_[A-Za-z0-9_-]{43}", content.get("gateway_token", ""))
    ):
        raise ValueError("Invalid local Gateway credential file")
    return content
