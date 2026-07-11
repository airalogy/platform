import json

from app.libs.safe_logging import (
    safe_json_body,
    safe_path,
    safe_query_string,
    safe_request_target,
)


def test_safe_json_body_redacts_nested_secrets():
    logged = safe_json_body(
        json.dumps(
            {
                "email": "researcher@example.org",
                "password": "secret-password",
                "nested": {"inviteToken": "invite-secret", "value": 3},
            }
        ).encode()
    )

    assert "secret-password" not in logged
    assert "invite-secret" not in logged
    assert logged.count("[REDACTED]") == 2
    assert "researcher@example.org" in logged


def test_safe_query_string_redacts_tokens_and_passwords():
    logged = safe_query_string("token=secret&project=alpha&current_password=hidden")

    assert "secret" not in logged
    assert "hidden" not in logged
    assert "project=alpha" in logged


def test_safe_json_body_does_not_echo_invalid_payloads():
    assert safe_json_body(b"not-json") == "[UNAVAILABLE]"


def test_safe_path_redacts_invitation_and_password_reset_tokens():
    invitation = safe_path("/instance/invitations/invite-secret/accept")
    password_reset = safe_path("/instance/password-resets/reset-secret")

    assert "invite-secret" not in invitation
    assert "reset-secret" not in password_reset
    assert invitation == "/instance/invitations/[REDACTED]/accept"


def test_safe_request_target_redacts_path_and_query_tokens():
    target = safe_request_target(
        "/instance/invitations/path-secret?token=query-secret&project=alpha"
    )

    assert "path-secret" not in target
    assert "query-secret" not in target
    assert "project=alpha" in target
