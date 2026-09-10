"""Owned local developer UI coordination; no hardware or paid model calls."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from test_package_authoring import FixtureClient, fixture_test, proposal, spec
from test_package_installation import sdk

from airalogy_instrument_gateway import authoring
from airalogy_instrument_gateway.authoring_workspace import AuthoringWorkspace
from airalogy_instrument_gateway.package_contract import sha256
from airalogy_instrument_gateway.package_sandbox import SandboxError
from airalogy_instrument_gateway.state import StateStore


class AuthoringWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.workspace = AuthoringWorkspace(self.root)
        wheel = sdk()
        self.inputs = {
            "platform_url": "https://lab.example.edu/api",
            "gateway_id": str(uuid4()),
            "resource_id": str(uuid4()),
            "trusted_sdk_digest": sha256(wheel),
            "image": "sha256:" + "1" * 64,
            "max_iterations": 3,
            "duration_seconds": 900,
            "timeout_seconds": 30,
            "spec": self.workspace.upload("spec", json.dumps(spec()).encode())["path"],
            "sdk_wheel": self.workspace.upload("sdk_wheel", wheel)["path"],
        }

    def prepare(self):
        preview = self.workspace.dispatch("prepare-preview", self.inputs)
        return self.workspace.dispatch(
            "prepare-confirm", {"confirmation": preview["confirmation"]}
        )

    def run_worker(self, session, client, *, tester=fixture_test, reconcile=False):
        original = authoring.run
        with (
            patch.object(authoring, "AuthoringClient", return_value=client),
            patch.object(
                authoring,
                "run",
                side_effect=lambda path, **kw: original(
                    path, client=client, tester=tester, **kw
                ),
            ),
        ):
            preview = self.workspace.dispatch(
                "run-preview", {"id": session["id"], "reconcile": reconcile}
            )
            self.workspace.dispatch(
                "run-confirm", {"confirmation": preview["confirmation"]}
            )
            self.workspace.worker.join(timeout=10)
            self.assertFalse(self.workspace.worker.is_alive())
        return self.workspace.dispatch("state", {})["job"]

    def test_previews_are_side_effect_free_stale_safe_and_private(self):
        before = set(self.root.iterdir())
        preview = self.workspace.dispatch("prepare-preview", self.inputs)
        self.assertEqual(set(self.root.iterdir()), before)
        self.assertNotIn("authoring_token", json.dumps(preview))
        changed = spec()
        changed["goal"] = "Changed after preview"
        Path(self.inputs["spec"]).write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "changed after preview"):
            self.workspace.dispatch(
                "prepare-confirm", {"confirmation": preview["confirmation"]}
            )
        self.assertEqual(self.workspace.dispatch("state", {})["sessions"], [])
        session = self.prepare()
        request = authoring.read_request(self.root / session["id"] / "request.json")
        exported = self.workspace.dispatch(
            "download", {"id": session["id"], "kind": "authorization", "turn_id": None}
        )
        self.assertEqual(json.loads(exported.content), request["request"])
        self.assertNotIn(request["authoring_token"].encode(), exported.content)
        self.assertFalse(session["hardware_authorized"])
        self.assertFalse(session["activation_performed"])

    def test_invalid_form_shapes_and_known_credentials_do_not_enter_previews(self):
        for key in (
            "platform_url",
            "gateway_id",
            "resource_id",
            "trusted_sdk_digest",
            "image",
            "max_iterations",
            "duration_seconds",
            "timeout_seconds",
        ):
            for value in (None, [], {}, True):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.workspace.dispatch(
                        "prepare-preview", {**self.inputs, key: value}
                    )
        content = spec()
        content["materials"][0]["text"] = "aigw_" + "A" * 43
        Path(self.inputs["spec"]).write_text(json.dumps(content))
        with self.assertRaises(ValueError):
            self.workspace.dispatch("prepare-preview", self.inputs)
        self.assertEqual(self.workspace.dispatch("state", {})["sessions"], [])

    def test_runtime_roots_installation_operations_and_arbitrary_paths_are_refused(
        self,
    ):
        for operation in ("identity-preview", "pair", "installation-apply"):
            with self.assertRaises(ValueError):
                self.workspace.dispatch(operation, {})
        with self.assertRaises(ValueError):
            self.workspace.dispatch("inspect", {"id": "../../private"})
        with self.assertRaises(ValueError):
            self.workspace.upload("config", b"{}")
        (self.root / "gateway.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "separate development"):
            AuthoringWorkspace(self.root)

    def test_worker_builds_fixed_draft_downloads_and_restart_does_not_rerun(self):
        session = self.prepare()
        client = FixtureClient(
            session["authorization"], [proposal(broken=True), proposal()]
        )
        job = self.run_worker(session, client)
        self.assertEqual(job["result"]["state"], "draft_tested")
        self.assertEqual(len(client.turns), 2)
        restored = AuthoringWorkspace(self.root)
        self.assertIsNone(restored.dispatch("state", {})["job"])
        inspected = restored.dispatch("inspect", {"id": session["id"]})
        self.assertEqual(inspected["runs"][0]["result"]["state"], "draft_tested")
        self.assertEqual(inspected["runs"][0]["liveness"], "not_observed")
        good = next(
            item
            for item in inspected["artifacts"]
            if item["state"] == "locally_tested_draft"
        )
        bad = next(
            item for item in inspected["artifacts"] if item["state"] == "test_failed"
        )
        download = restored.dispatch(
            "download", {"id": session["id"], "turn_id": good["id"], "kind": "package"}
        )
        self.assertEqual(sha256(download.content), good["report"]["archive_digest"])
        with self.assertRaises(ValueError):
            restored.dispatch(
                "download",
                {"id": session["id"], "turn_id": bad["id"], "kind": "package"},
            )
        self.assertEqual(
            self.run_worker(session, client)["result"]["state"], "draft_tested"
        )
        self.assertEqual(len(client.turns), 2)
        (self.root / session["id"] / f"{good['id']}.zip").write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "differs"):
            restored.dispatch(
                "download",
                {"id": session["id"], "turn_id": good["id"], "kind": "package"},
            )

    def test_pause_and_duplicate_confirmation_use_the_observed_worker(self):
        session = self.prepare()
        client = FixtureClient(session["authorization"], [proposal()])
        entered, release = threading.Event(), threading.Event()
        original_run, original_call = authoring.run, client.call

        def delayed(operation, *args, **kwargs):
            if operation == "turns":
                entered.set()
                if not release.wait(timeout=10):
                    raise RuntimeError("Synthetic wait exceeded")
            return original_call(operation, *args, **kwargs)

        client.call = delayed
        with (
            patch.object(authoring, "AuthoringClient", return_value=client),
            patch.object(
                authoring,
                "run",
                side_effect=lambda path, **kw: original_run(
                    path, client=client, tester=fixture_test, **kw
                ),
            ),
        ):
            preview = self.workspace.dispatch(
                "run-preview", {"id": session["id"], "reconcile": False}
            )
            started = self.workspace.dispatch(
                "run-confirm", {"confirmation": preview["confirmation"]}
            )
            try:
                self.assertTrue(entered.wait(timeout=5))
                with self.assertRaises(ValueError):
                    self.workspace.dispatch(
                        "run-confirm", {"confirmation": preview["confirmation"]}
                    )
                with self.assertRaises(ValueError):
                    self.workspace.dispatch(
                        "run-preview", {"id": session["id"], "reconcile": False}
                    )
                result = self.workspace.dispatch("pause", {"id": started["job"]["id"]})
                self.assertTrue(result["worker_alive"])
                self.assertFalse(result["hardware_authorized"])
            finally:
                release.set()
                self.workspace.worker.join(timeout=10)
        self.assertEqual(self.workspace.job["result"]["state"], "locally_paused")
        self.assertEqual(client.report_calls, 0)
        self.assertEqual(
            self.run_worker(session, client)["result"]["state"], "draft_tested"
        )
        self.assertEqual(len(client.turns), 1)

    def test_existing_cli_lock_and_changed_request_fail_without_model_spend(self):
        session = self.prepare()
        client = FixtureClient(session["authorization"], [proposal()])
        with StateStore(self.root / session["id"] / "authoring.json").exclusive():
            self.assertEqual(
                self.run_worker(session, client)["result"]["state"], "needs_inspection"
            )
        self.assertEqual(client.turns, [])
        with patch.object(authoring, "AuthoringClient", return_value=client):
            preview = self.workspace.dispatch(
                "run-preview", {"id": session["id"], "reconcile": False}
            )
        path = self.root / session["id"] / "request.json"
        content = authoring.read_request(path)
        content["platform_url"] = "https://changed.example.edu/api"
        path.write_text(json.dumps(content))
        with self.assertRaisesRegex(ValueError, "changed after preview"):
            self.workspace.dispatch(
                "run-confirm", {"confirmation": preview["confirmation"]}
            )

    def test_only_previewed_uncertain_test_can_be_reconciled(self):
        session = self.prepare()
        client = FixtureClient(session["authorization"], [proposal(), proposal()])

        def interrupted(*args, **kwargs):
            raise SandboxError("Synthetic interrupted isolated test")

        self.assertEqual(
            self.run_worker(session, client, tester=interrupted)["result"]["state"],
            "needs_inspection",
        )
        path = self.root / session["id"] / "request.json"
        with patch.object(authoring, "reconcile_sandbox") as stop:
            with self.assertRaisesRegex(ValueError, "confirmed preview"):
                authoring.run(
                    path,
                    client=client,
                    tester=fixture_test,
                    reconcile=True,
                    reconcile_turn_ids=[],
                )
            stop.assert_not_called()
            self.assertEqual(
                self.run_worker(session, client, reconcile=True)["result"]["state"],
                "draft_tested",
            )
            stop.assert_called_once_with(client.turns[0]["id"])
        self.assertFalse(client.turns[0]["report"]["passed"])

    def test_missing_information_is_visible_without_fabricated_passing_artifacts(self):
        session = self.prepare()
        client = FixtureClient(session["authorization"], [proposal(missing=True)])
        result = self.run_worker(session, client)
        self.assertEqual(result["result"]["state"], "needs_information")
        inspected = self.workspace.dispatch("inspect", {"id": session["id"]})
        item = inspected["artifacts"][0]
        self.assertEqual(item["state"], "needs_information")
        self.assertEqual(
            item["proposal"]["missing_information"],
            ["Provide the real device completion contract"],
        )
        self.assertNotIn("report", item)
        self.assertEqual(client.report_calls, 0)
        with self.assertRaises(ValueError):
            self.workspace.dispatch(
                "download",
                {"id": session["id"], "turn_id": item["id"], "kind": "package"},
            )


if __name__ == "__main__":
    unittest.main()
