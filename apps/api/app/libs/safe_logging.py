import json
import re
from collections.abc import Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth_token",
    "authorization",
    "code",
    "confirm_password",
    "confirmpassword",
    "current_password",
    "invite_token",
    "password",
    "refresh_token",
    "secret",
    "setup_token",
    "token",
    "verify_code",
}
MAX_LOGGED_BODY_LENGTH = 4096
SENSITIVE_PATH_PATTERNS = (
    re.compile(r"(?P<prefix>/instance/invitations/)[^/?#]+"),
    re.compile(r"(?P<prefix>/instance/password-resets/)[^/?#]+"),
)


def is_sensitive_key(key: object) -> bool:
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(key))
    normalized = normalized.lower().replace("-", "_")
    return normalized in SENSITIVE_KEYS or normalized.endswith("_password")


def redact_value(value):
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if is_sensitive_key(key) else redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_value(item) for item in value]
    return value


def safe_json_body(raw_body: bytes) -> str:
    try:
        parsed = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "[UNAVAILABLE]"
    serialized = json.dumps(redact_value(parsed), ensure_ascii=False, separators=(",", ":"))
    if len(serialized) > MAX_LOGGED_BODY_LENGTH:
        return f"{serialized[:MAX_LOGGED_BODY_LENGTH]}...[TRUNCATED]"
    return serialized


def safe_query_string(query_string: str) -> str:
    if not query_string:
        return ""
    return urlencode(
        [
            (key, "[REDACTED]" if is_sensitive_key(key) else value)
            for key, value in parse_qsl(query_string, keep_blank_values=True)
        ]
    )


def safe_path(path: str) -> str:
    redacted = path
    for pattern in SENSITIVE_PATH_PATTERNS:
        redacted = pattern.sub(r"\g<prefix>[REDACTED]", redacted)
    return redacted


def safe_request_target(target: str) -> str:
    parsed = urlsplit(target)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            safe_path(parsed.path),
            safe_query_string(parsed.query),
            parsed.fragment,
        )
    )
