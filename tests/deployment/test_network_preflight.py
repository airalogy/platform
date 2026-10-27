"""Synthetic network/transport tests; no host or Docker mutation."""

import contextlib
import copy
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/single-lab/scripts/network_preflight.py"
spec = importlib.util.spec_from_file_location("network_preflight", SCRIPT)
guard = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = (
    True  # Do not contaminate the copied release deployment directory.
)
spec.loader.exec_module(guard)


def config(subnet="192.168.246.0/24"):
    return {
        "name": "fixture",
        "services": {
            "api": {
                "environment": {
                    "DATABASE_URL": "postgresql://fixture:private-fixture-secret@db/example"
                }
            },
            "db": {},
        },
        "networks": {
            "default": {
                "name": "fixture_default",
                "ipam": {"config": [{"subnet": subnet}]},
            }
        },
    }


def existing(subnet="192.168.246.0/24"):
    return {
        "Name": "fixture_default",
        "Id": "abcdef123456" + "0" * 52,
        "Driver": "bridge",
        "Options": {},
        "Labels": {
            "com.docker.compose.project": "fixture",
            "com.docker.compose.network": "default",
        },
        "IPAM": {
            "Config": [
                {
                    "Subnet": subnet,
                    "Gateway": str(guard.network(subnet, "test").network_address + 1),
                }
            ]
        },
    }


class NetworkGateTests(unittest.TestCase):
    def test_nonoverlapping_plan_and_default_routes(self):
        guard.check(
            guard.plans(config()),
            [guard.network("10.0.0.0/8", "test")],
            routes=[{"dst": "default"}, {"dst": "10.1.0.0/16", "dev": "eth0"}],
        )

    def test_automatic_allocation_is_rejected_before_creation(self):
        c = config()
        c["networks"]["default"]["ipam"] = {}
        with self.assertRaisesRegex(guard.CheckError, "explicit IPAM"):
            guard.plans(c)

    def test_incident_network_cannot_cover_vpc_or_rds(self):
        plan = guard.plans(config("172.20.0.0/16"))
        with self.assertRaisesRegex(guard.CheckError, "protected/cloud"):
            guard.check(plan, [guard.network("172.16.0.0/12", "test")])
        with self.assertRaisesRegex(guard.CheckError, "external service"):
            guard.check(plan, [], endpoints=[guard.ipaddress.ip_address("172.20.50.5")])

    def test_subset_superset_and_exact_conflicts(self):
        for block in ("192.168.0.0/16", "192.168.246.128/25", "192.168.246.0/24"):
            with self.subTest(block=block), self.assertRaises(guard.CheckError):
                guard.check(guard.plans(config()), [guard.network(block, "test")])

    def test_routes_interfaces_and_other_docker_networks(self):
        plan = guard.plans(config())
        checks = [
            {"routes": [{"dst": "192.168.0.0/16", "dev": "tun0"}]},
            {
                "addresses": [
                    {
                        "ifname": "eth1",
                        "addr_info": [
                            {
                                "family": "inet",
                                "local": "192.168.246.8",
                                "prefixlen": 24,
                            }
                        ],
                    }
                ]
            },
            {"existing": [existing()]},
        ]
        for inputs in checks:
            with self.subTest(inputs=inputs), self.assertRaises(guard.CheckError):
                guard.check(plan, [], **inputs)

    def test_exact_own_network_can_be_reused_but_never_hides_cloud_conflict(self):
        actual = existing()
        plan = guard.plans(config(), [actual])
        routes = [
            {"dst": "192.168.246.0/24", "dev": "br-abcdef123456"},
            {"dst": "192.168.246.1", "dev": "br-abcdef123456", "type": "local"},
        ]
        addresses = [
            {
                "ifname": "br-abcdef123456",
                "addr_info": [
                    {"family": "inet", "local": "192.168.246.1", "prefixlen": 24}
                ],
            }
        ]
        guard.check(plan, [], [actual], routes, addresses)
        with self.assertRaisesRegex(guard.CheckError, "protected/cloud"):
            guard.check(
                plan,
                [guard.network("192.168.0.0/16", "test")],
                [actual],
                routes,
                addresses,
            )
        with self.assertRaisesRegex(guard.CheckError, "host route"):
            guard.check(
                plan,
                [],
                [actual],
                [{"dst": "192.168.0.0/16", "dev": "br-abcdef123456"}],
            )

    def test_another_bridge_or_gateway_route_is_not_exempt(self):
        actual = existing()
        plan = guard.plans(config(), [actual])
        for route in [
            {"dst": "192.168.246.2", "dev": "br-other"},
            {
                "dst": "192.168.246.2",
                "dev": "br-abcdef123456",
                "gateway": "192.168.246.5",
            },
        ]:
            with self.subTest(route=route), self.assertRaises(guard.CheckError):
                guard.check(plan, [], [actual], [route])

    def test_same_name_different_owner_or_live_subnet_requires_migration(self):
        actual = existing()
        actual["Labels"]["com.docker.compose.project"] = "other"
        with self.assertRaisesRegex(guard.CheckError, "another deployment"):
            guard.plans(config(), [actual])
        with self.assertRaisesRegex(guard.CheckError, "maintenance migration"):
            guard.plans(config(), [existing("192.168.245.0/24")])
        desired = config()
        desired["networks"]["default"]["ipam"]["config"][0]["gateway"] = "192.168.246.2"
        with self.assertRaisesRegex(guard.CheckError, "IPAM gateway differs"):
            guard.plans(desired, [existing()])

    def test_external_network_must_exist_and_is_still_checked(self):
        c = config()
        c["networks"]["default"] = {"name": "fixture_default", "external": True}
        with self.assertRaisesRegex(guard.CheckError, "does not exist"):
            guard.plans(c, [])
        with self.assertRaises(guard.CheckError):
            guard.check(
                guard.plans(c, [existing()]), [guard.network("192.168.0.0/16", "test")]
            )

    def test_overlapping_planned_networks_and_pools(self):
        c = config()
        c["networks"]["second"] = copy.deepcopy(c["networks"]["default"])
        with self.assertRaisesRegex(guard.CheckError, "another planned"):
            guard.check(guard.plans(c), [])
        c = config()
        c["networks"]["default"]["ipam"]["config"].append(
            {"subnet": "192.168.246.0/25"}
        )
        with self.assertRaisesRegex(guard.CheckError, "overlapping IPAM"):
            guard.plans(c)

    def test_unsupported_or_invalid_subnets_never_pass(self):
        for subnet in [
            "192.168.246.4/24",
            "8.0.0.0/8",
            "127.0.0.0/8",
            "192.168.246.0/32",
            "fd00::/64",
            "bad",
        ]:
            with self.subTest(subnet=subnet), self.assertRaises(guard.CheckError):
                guard.plans(config(subnet))

    def test_dns_checks_every_address_and_does_not_print_credentials(self):
        responses = [
            (2, 1, 6, "", ("192.168.246.5", 0)),
            (2, 1, 6, "", ("10.3.4.5", 0)),
        ]
        with patch.object(guard.socket, "getaddrinfo", return_value=responses) as dns:
            values = guard.resolve_endpoints(
                config(),
                ["postgresql://user:private-fixture-secret@db.example.invalid/data"],
            )
            self.assertEqual(len(values), 2)
            dns.assert_called_once()  # Internal service 'db' is not resolved on host.
        with patch.object(
            guard.socket, "getaddrinfo", side_effect=OSError("private-fixture-secret")
        ):
            with self.assertRaises(guard.CheckError) as result:
                guard.resolve_endpoints(
                    config(),
                    [
                        "postgresql://user:private-fixture-secret@db.example.invalid/data"
                    ],
                )
            self.assertNotIn("private-fixture-secret", str(result.exception))

    def test_cloud_failure_is_closed_and_never_echoes_token(self):
        with patch.object(
            guard.urllib.request.OpenerDirector,
            "open",
            side_effect=OSError("private-fixture-secret"),
        ):
            with self.assertRaisesRegex(
                guard.CheckError, "deployment blocked"
            ) as error:
                guard.aliyun_vpc()
            self.assertNotIn("private-fixture-secret", str(error.exception))

    def test_cloud_security_token_and_vpc_only(self):
        responses = [
            contextlib.closing(io.BytesIO(b"fixture-token")),
            contextlib.closing(io.BytesIO(b"172.16.0.0/12")),
        ]
        with patch.object(
            guard.urllib.request.OpenerDirector, "open", side_effect=responses
        ) as request:
            self.assertEqual(str(guard.aliyun_vpc()), "172.16.0.0/12")
            self.assertEqual(request.call_args_list[0].args[0].method, "PUT")
            self.assertTrue(
                request.call_args_list[1].args[0].full_url.endswith("vpc-cidr-block")
            )
        with self.assertRaises(guard.CheckError):
            guard.NoRedirect().redirect_request(None, None, None, None, None, None)

    def test_operator_must_explicitly_classify_extra_networks(self):
        with (
            patch.object(guard, "command", return_value=""),
            self.assertRaisesRegex(guard.CheckError, "PROTECTED_CIDRS"),
        ):
            guard.settings(["docker", "compose"])
        with patch.object(
            guard, "command", return_value="NETWORK_PREFLIGHT_PROTECTED_CIDRS=none\n"
        ):
            self.assertEqual(guard.settings([]), ("none", [], []))

    def test_remote_context_cannot_check_local_routes(self):
        for result in ["ssh://remote", "tcp://remote:2376"]:
            with (
                patch.object(guard.platform, "system", return_value="Linux"),
                patch.object(guard.Path, "exists", return_value=False),
                patch.dict(
                    guard.os.environ, {"DOCKER_HOST": result, "DOCKER_CONTEXT": ""}
                ),
                self.assertRaisesRegex(guard.CheckError, "Remote Docker"),
            ):
                guard.live_inventory()

    def test_rootless_and_desktop_daemons_cannot_validate_host_routes(self):
        for info in [
            {"OSType": "linux", "SecurityOptions": ["name=rootless"]},
            {"OSType": "linux", "OperatingSystem": "Docker Desktop"},
        ]:
            with (
                patch.object(guard.platform, "system", return_value="Linux"),
                patch.object(guard.Path, "exists", return_value=False),
                patch.dict(
                    guard.os.environ,
                    {
                        "DOCKER_HOST": "unix:///var/run/docker.sock",
                        "DOCKER_CONTEXT": "",
                    },
                ),
                patch.object(guard, "json_command", return_value=info),
                self.assertRaisesRegex(guard.CheckError, "regular Linux Docker"),
            ):
                guard.live_inventory()

    def test_config_only_never_claims_host_verified_or_calls_metadata(self):
        with (
            patch.object(
                guard.sys, "argv", ["guard", "--config-only", "--", "docker", "compose"]
            ),
            patch.object(guard, "json_command", return_value=config()),
            patch.object(guard, "settings", return_value=("aliyun", [], [])),
            patch.object(guard, "live_inventory") as live,
            patch.object(guard, "aliyun_vpc") as metadata,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            guard.main()
            live.assert_not_called()
            metadata.assert_not_called()
            self.assertIn("NOT checked", output.getvalue())

    def test_command_failures_do_not_echo_resolved_environment(self):
        failure = subprocess.CompletedProcess(
            [], 1, "", "password=private-fixture-secret"
        )
        with patch.object(guard.subprocess, "run", return_value=failure):
            with self.assertRaises(guard.CheckError) as error:
                guard.command(["docker", "compose", "config"])
            self.assertNotIn("private-fixture-secret", str(error.exception))

    def test_platform_compose_gate_blocks_up_before_docker_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "env").write_text("NETWORK_PREFLIGHT_PROTECTED_CIDRS=none\n")
            fake = root / "docker"
            fake.write_text(
                "#!/bin/sh\ncase \"$*\" in\n *'config --format json'*) printf '%s' '{}' ;;\n *'config --environment'*) printf '%s' 'NETWORK_PREFLIGHT_PROTECTED_CIDRS=none' ;;\n *) echo forbidden-mutation >&2; exit 99 ;;\nesac\n"
            )
            fake.chmod(0o755)
            env = dict(
                guard.os.environ,
                PATH=f"{root}:{guard.os.environ['PATH']}",
                AIRALOGY_ENV_FILE=str(root / "env"),
            )
            script = (
                f'source "{ROOT}/deploy/single-lab/scripts/lib.sh"\ncompose up -d\n'
            )
            result = subprocess.run(
                ["bash", "-c", script],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("forbidden-mutation", result.stdout + result.stderr)

    def test_all_stop_before_restore_paths_have_an_early_gate(self):
        for name, first_mutation in [
            ("restore.sh", "compose stop"),
            ("rollback.sh", "restore_storage_snapshot"),
        ]:
            source = (ROOT / "deploy/single-lab/scripts" / name).read_text()
            self.assertLess(
                source.index("network_preflight"), source.index(first_mutation)
            )
        for name in ("start.sh", "upgrade.sh"):
            source = (ROOT / "deploy/single-lab/scripts" / name).read_text()
            self.assertLess(
                source.index('"$SCRIPT_DIR/preflight.sh"'), source.index("compose ")
            )


if __name__ == "__main__":
    unittest.main()
