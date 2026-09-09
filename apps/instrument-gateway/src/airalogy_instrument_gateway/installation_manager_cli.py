"""Prepare a public installation request, then apply its independently reviewed grant."""

import argparse
import json
import sys
from pathlib import Path

from .client import GatewayAPIError
from .installation_manager import InstallationClient, apply, prepare, read_request


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    create = sub.add_parser("prepare")
    for name in ["platform-url", "lab-id", "gateway-id", "trusted-sdk-digest"]:
        create.add_argument(f"--{name}", required=True)
    for name in ["destination", "package", "sdk-wheel", "config", "root"]:
        create.add_argument(f"--{name}", type=Path, required=True)
    for operation in ["request", "status", "apply"]:
        command = sub.add_parser(operation)
        command.add_argument("private_request", type=Path)
        if operation == "apply":
            command.add_argument("--source-reviewed", action="store_true")
    args = vars(parser.parse_args(argv))
    operation = args.pop("operation")
    try:
        if operation == "prepare":
            result = prepare(**args)
        elif operation == "apply":
            result = apply(
                args["private_request"], source_reviewed=args["source_reviewed"]
            )
        else:
            content = read_request(args["private_request"])
            result = (
                content["request"]
                if operation == "request"
                else InstallationClient(content).call("status")
            )
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (ValueError, TypeError, KeyError, OSError, GatewayAPIError) as error:
        print(f"Installation manager failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
