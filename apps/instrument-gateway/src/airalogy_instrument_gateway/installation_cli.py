"""Preview and create an inactive local installation, without enabling equipment."""

import argparse
import json
import sys
from pathlib import Path

from .package_cli import read_selected
from .package_contract import strict_json
from .package_installation import install_inactive, installation_preview


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["preview", "install"])
    parser.add_argument("package", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--sdk-wheel", type=Path, required=True)
    parser.add_argument("--trusted-sdk-sha256", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--confirm-digest")
    parser.add_argument("--source-reviewed", action="store_true")
    args = parser.parse_args(argv)
    try:
        raw = read_selected(args.package)
        inputs = {
            "sdk_wheel": read_selected(args.sdk_wheel),
            "trusted_sdk_digest": args.trusted_sdk_sha256,
            "config": strict_json(read_selected(args.config, limit=16384)),
            "root": args.root,
        }
        if args.operation == "preview":
            result = installation_preview(raw, **inputs)
        else:
            if not args.confirm_digest:
                raise ValueError(
                    "Read the preview first and supply its exact confirmation digest"
                )
            result = install_inactive(
                raw,
                **inputs,
                preview_digest=args.confirm_digest,
                source_reviewed=args.source_reviewed,
            )
        # Configuration contents and wheel source never enter diagnostics.
        print(
            json.dumps(
                {key: value for key, value in result.items() if key != "files"},
                ensure_ascii=True,
                indent=2,
            )
        )
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"Inactive installation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
