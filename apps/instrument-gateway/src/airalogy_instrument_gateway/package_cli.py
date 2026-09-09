"""Build, inspect and sandbox-test selected adapter packages. Never install here."""

import argparse
import json
import os
import stat
import sys
from pathlib import Path

from .package_builder import build_package
from .package_contract import MAX_ARCHIVE_BYTES, inspect_package, safe_path, strict_json
from .package_sandbox import SandboxError, test_package


def read_selected(path, *, limit=MAX_ARCHIVE_BYTES):
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise ValueError("Selected input must be a bounded regular file")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size > limit
            or (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino)
        ):
            raise ValueError("Selected input must be a bounded regular file")
        value = source.read(limit + 1)
        if len(value) > limit:
            raise ValueError("Input grew beyond its limit")
        return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--manifest", type=Path, required=True)
    build.add_argument("--factory", required=True)
    build.add_argument(
        "--file",
        action="append",
        required=True,
        help="Explicit archive/path=/absolute/selected/file; no recursive scans",
    )
    build.add_argument("--output", type=Path, required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("package", type=Path)
    test = commands.add_parser("test")
    test.add_argument("package", type=Path)
    test.add_argument("--sdk-wheel", type=Path, required=True)
    test.add_argument("--trusted-sdk-sha256", required=True)
    test.add_argument("--image", required=True)
    test.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            manifest = strict_json(read_selected(args.manifest, limit=256 * 1024))
            payloads = {}
            for entry in args.file:
                name, separator, selected = entry.partition("=")
                if not separator or name in payloads:
                    raise ValueError(
                        "Each input requires a unique archive/path=selected/file mapping"
                    )
                payloads[safe_path(name)] = read_selected(Path(selected))
            raw, result = build_package(
                manifest, factory=args.factory, payloads=payloads
            )
            # No overwrite of a reviewed/published version or another local artifact.
            descriptor = os.open(
                args.output,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(descriptor, "wb") as target:
                target.write(raw)
                target.flush()
                os.fsync(target.fileno())
        elif args.command == "inspect":
            result = inspect_package(read_selected(args.package))
        else:
            result = test_package(
                read_selected(args.package),
                sdk_wheel=read_selected(args.sdk_wheel),
                trusted_sdk_digest=args.trusted_sdk_sha256,
                image=args.image,
                timeout_seconds=args.timeout,
            )
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 1 if result.get("passed") is False else 0
    except (OSError, ValueError, KeyError, SandboxError) as error:
        print(f"Adapter package operation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
