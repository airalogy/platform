"""Offline inspection/rehearsal of selected JSON files, never device control."""

import argparse
import json
import os
import stat
from pathlib import Path

from .integration_contract import MAX_BYTES, canonical, example_bundle, rehearse


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "bundle",
        nargs="?",
        type=Path,
        help="Selected rehearsal JSON file (not a directory)",
    )
    parser.add_argument(
        "--example", action="store_true", help="Print a synthetic example"
    )
    args = parser.parse_args()
    if args.example:
        if args.bundle:
            parser.error("Choose either --example or a bundle")
        print(json.dumps(example_bundle(), indent=2, ensure_ascii=False))
        return
    if args.bundle is None:
        parser.error("Select a bundle or --example")
    try:
        # Never follow a final symlink or scan adjacent paths. The explicitly
        # selected file may contain only data; no referenced paths are opened.
        selected = args.bundle.lstat()
        if not stat.S_ISREG(selected.st_mode):
            raise ValueError("Select a regular file, not a symlink")
        descriptor = os.open(
            args.bundle,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (
                selected.st_dev,
                selected.st_ino,
            ) != (opened.st_dev, opened.st_ino):
                raise ValueError("Selected file changed before reading")
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("Bundle exceeds the 256 KiB limit")
        bundle = json.loads(data)
        canonical(bundle)
        if not isinstance(bundle, dict) or set(bundle) != {"package", "scenarios"}:
            raise ValueError("Expected package and scenarios")
        report = rehearse(bundle["package"], bundle["scenarios"])
    except (ValueError, OSError, TypeError) as error:
        parser.exit(2, f"Rehearsal rejected: {error}\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["passed"]:
        parser.exit(1)


if __name__ == "__main__":
    main()
