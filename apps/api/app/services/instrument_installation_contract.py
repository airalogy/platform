"""Private installation requests/receipts, shared verbatim with the API.

Only digests and bounded identities cross this boundary, never local paths,
configuration contents or execution credentials. This is not device attestation.
"""

import hashlib
import json
import re
from uuid import UUID

IDENTITY_FIELDS = (
    "archive_digest",
    "manifest_digest",
    "sdk_digest",
    "configuration_digest",
    "python_version",
    "platform",
    "architecture",
    "interpreter_digest",
    "entry_point",
)
DESCRIPTOR_FIELDS = (*IDENTITY_FIELDS, "installation_id", "local_preview_digest")
HEX = re.compile(r"^[a-f0-9]{64}$")


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _keys(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError("Installation document has missing or unsupported fields")


def descriptor_from_preview(preview):
    return validate_descriptor(
        {
            **{key: preview[key] for key in IDENTITY_FIELDS},
            "installation_id": preview["installation_id"],
            "local_preview_digest": preview["preview_digest"],
        }
    )


def validate_descriptor(value):
    _keys(value, DESCRIPTOR_FIELDS)
    for key, item in value.items():
        if not isinstance(item, str):
            # Pydantic maps ValueError, not TypeError, to a client validation error.
            raise ValueError("Installation descriptor fields must be strings")  # noqa: TRY004
        if (key.endswith("digest") or key == "installation_id") and not HEX.fullmatch(
            item
        ):
            raise ValueError("Invalid installation digest")
    if not re.fullmatch(r"3\.\d{1,2}\.\d{1,3}", value["python_version"]):
        raise ValueError("Installation requires an exact Python version")
    if value["platform"] not in {"linux", "darwin"} or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,64}", value["architecture"]
    ):
        raise ValueError("Unsupported installation platform/architecture")
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,127}", value["entry_point"]):
        raise ValueError("Invalid installation entry point")
    identity = {
        "schema": "airalogy.inactive-installation.v1",
        **{key: value[key] for key in IDENTITY_FIELDS},
    }
    if digest(identity) != value["installation_id"]:
        raise ValueError("Installation identity does not match its descriptor")
    return dict(value)


def request_fingerprint(request):
    return digest(
        {key: value for key, value in request.items() if key != "fingerprint"}
    )


def validate_request(value):
    _keys(
        value,
        [
            "schema",
            "id",
            "lab_id",
            "gateway_id",
            "credential_digest",
            "descriptor",
            "fingerprint",
        ],
    )
    if value["schema"] != "airalogy.installation-request.v1":
        raise ValueError("Unsupported public installation request")
    for key in ["id", "lab_id", "gateway_id"]:
        if not isinstance(value[key], str) or str(UUID(value[key])) != value[key]:
            raise ValueError("Installation request requires canonical UUIDs")
    if not isinstance(value["credential_digest"], str) or not HEX.fullmatch(
        value["credential_digest"]
    ):
        raise ValueError("Invalid installation credential digest")
    validate_descriptor(value["descriptor"])
    if value["fingerprint"] != request_fingerprint(value):
        raise ValueError("Installation request fingerprint changed")
    return value


def receipt_summary(receipt):
    """Exclude filesystem paths and file inventory from the server receipt."""
    descriptor = descriptor_from_preview(receipt)
    return {
        "schema": "airalogy.installation-receipt.v1",
        "descriptor": descriptor,
        "local_receipt_digest": digest(receipt),
        "installed_file_count": receipt["installed_file_count"],
        "installed_bytes": receipt["installed_bytes"],
        "activation_performed": False,
        "hardware_authorized": False,
    }


def validate_receipt(value):
    _keys(
        value,
        [
            "schema",
            "descriptor",
            "local_receipt_digest",
            "installed_file_count",
            "installed_bytes",
            "activation_performed",
            "hardware_authorized",
        ],
    )
    if value["schema"] != "airalogy.installation-receipt.v1":
        raise ValueError("Unsupported installation receipt")
    validate_descriptor(value["descriptor"])
    if not isinstance(value["local_receipt_digest"], str) or not HEX.fullmatch(
        value["local_receipt_digest"]
    ):
        raise ValueError("Invalid local receipt digest")
    for key, limit in [
        ("installed_file_count", 8192),
        ("installed_bytes", 512 * 1024 * 1024),
    ]:
        if type(value[key]) is not int or not 1 <= value[key] <= limit:
            raise ValueError("Installation receipt exceeds supported limits")
    if (
        value["activation_performed"] is not False
        or value["hardware_authorized"] is not False
    ):
        raise ValueError(
            "Installation receipt cannot grant activation or hardware authority"
        )
    return value
