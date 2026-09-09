"""Prepare or resume an explicitly authorized source-development session."""

import argparse
import json
import sys
from pathlib import Path

from .authoring import AuthoringClient, prepare, read_request, run
from .client import GatewayAPIError
from .package_sandbox import SandboxError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("prepare")
    for name in ("workspace", "spec", "sdk-wheel"):
        create.add_argument("--" + name, type=Path, required=True)
    for name in (
        "platform-url",
        "gateway-id",
        "resource-id",
        "trusted-sdk-digest",
        "image",
    ):
        create.add_argument("--" + name, required=True)
    create.add_argument("--max-iterations", type=int, default=3)
    create.add_argument("--duration-seconds", type=int, default=900)
    create.add_argument("--timeout-seconds", type=int, default=60)
    execute = commands.add_parser("run")
    execute.add_argument("request", type=Path)
    execute.add_argument(
        "--reconcile-test",
        action="store_true",
        help="Stop only this session's journaled uncertain test; record failure, never assume a pass",
    )
    status = commands.add_parser("status")
    status.add_argument("request", type=Path)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    try:
        if command == "prepare":
            result = prepare(**args)
        elif command == "run":
            result = run(args["request"], reconcile=args["reconcile_test"])
        else:
            result = AuthoringClient(read_request(args["request"])).call("status")
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0 if result.get("state") in {None, "open", "draft_tested"} else 1
    except (OSError, ValueError, KeyError, GatewayAPIError, SandboxError) as error:
        print(f"Source authoring stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
