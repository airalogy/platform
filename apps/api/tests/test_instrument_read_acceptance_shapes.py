"""Acceptance fixtures stay distinct even when graphical tests are not opted in."""

from tests.http_read_acceptance import expected_interface_result


def test_native_fixture_does_not_require_a_browser_workflow():
    result = expected_interface_result(
        "owned-job", {"native_read": True, "definition_digest": "a" * 64}
    )
    assert result["definition_digest"] == "a" * 64
    assert "workflow_digest" not in result
    assert result["values"] == {"reader.status": "Ready", "reader.result": "No result"}
    assert result["observation_only"] is True


def test_browser_fixture_does_not_require_a_native_definition():
    result = expected_interface_result("owned-job", {"workflow_digest": "b" * 64})
    assert result["workflow_digest"] == "b" * 64
    assert "definition_digest" not in result
    assert result["value"] == 0.84
