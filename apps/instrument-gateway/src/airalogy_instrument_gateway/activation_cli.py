"""Preview and explicitly start one approved installed version; never hot-reload."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .installation_manager import read_request
from .managed_runtime import inspect_start
from .state import StateStore

# -I ignores Python environment/cwd, -S avoids site startup hooks, -B prevents
# bytecode from mutating the verified snapshot. Only verified wheel files join
# the standard library path. No shell or model-supplied program is executed.
BOOTSTRAP = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('airalogy_instrument_gateway.managed_runtime',run_name='__main__')"


def launch_command(local, arguments):
    _request, _credentials, inputs, descriptor, receipt = local
    site = inputs["root"] / descriptor["installation_id"] / receipt["site_packages"]
    return [sys.executable, "-I", "-S", "-B", "-c", BOOTSTRAP, str(site), *arguments]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["preview", "run"])
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--activation", required=True)
    parser.add_argument("--confirm-digest")
    parser.add_argument("--startup-authorized", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args(argv)
    try:
        request = read_request(args.request)
        with StateStore(Path(request["root"]) / "state.json").exclusive():
            preview, _response, local, _saved = inspect_start(
                args.request, args.credentials, args.activation, recover=args.recover
            )
            if args.operation == "preview":
                print(json.dumps(preview, ensure_ascii=True, indent=2))
                return 0
            if (
                not args.startup_authorized
                or args.confirm_digest != preview["preview_digest"]
            ):
                raise ValueError(
                    "Review the startup impact, explicitly authorize startup and confirm its exact digest"
                )
            arguments = [
                "--request",
                str(args.request.absolute()),
                "--credentials",
                str(args.credentials.absolute()),
                "--activation",
                args.activation,
                "--confirm-digest",
                args.confirm_digest,
            ]
            if args.once:
                arguments.append("--once")
            if args.recover:
                arguments.append("--recover")
            command = launch_command(local, arguments)
        # The child reacquires the same lock and verifies all bytes/authority
        # before driver import. A concurrent install/start in this gap fails
        # closed; the parent never imports the selected driver.
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("PYTHON", "AIRALOGY_GATEWAY_", "DYLD_", "LD_"))
        }
        return subprocess.call(command, env=environment, cwd=request["root"])
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as error:
        print(f"Managed activation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
