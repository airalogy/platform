"""Lossless tabular import preparation. No Protocol code or scientific inference."""

import csv
import hashlib
import hmac
import io
import json
import time
from collections import Counter
from typing import Any

MAX_IMPORT_BYTES = 20 * 1024 * 1024
MAX_IMPORT_ROWS = 10000
MAX_IMPORT_COLUMNS = 512
EXCEL_ERRORS = {
    "#REF!", "#VALUE!", "#DIV/0!", "#N/A", "#NAME?",
    "#NUM!", "#NULL!", "#SPILL!", "#CALC!",
}


def issue(code, column=None, row_number=None, line_number=None, message=""):
    return dict(
        code=code, column=column, row_number=row_number,
        line_number=line_number, message=message or code,
    )


def import_fields(schema: dict) -> list[dict]:
    variables = schema.get("vars") or {}
    required = set(variables.get("required") or [])
    return [
        dict(id=name, title=spec.get("title") or name, required=name in required, schema=spec)
        for name, spec in (variables.get("properties") or {}).items()
    ]


def template_csv(schema: dict) -> str:
    output = io.StringIO(newline="")
    # Explicit paths also prevent spreadsheet formula interpretation of headers.
    csv.writer(output).writerow([f"var.{field['id']}" for field in import_fields(schema)])
    return output.getvalue()


def _target_id(value: str) -> str:
    if value.startswith("data.var."):
        return value[9:]
    if value.startswith("var."):
        return value[4:]
    return value


def _is_record_path(value: str) -> bool:
    value = value.removeprefix("data.")
    return value in {"record_id", "record_version", "airalogy_record_id"} or any(
        value.startswith(prefix) and len(value) > len(prefix)
        for prefix in ("metadata.", "quiz.", "step.", "check.")
    )


def prepare_tabular(content: bytes, input_format: str, schema: dict) -> dict:
    """Require canonical IDs/paths; never guess titles or discard unknown columns."""
    result: dict[str, Any] = dict(errors=[], row_count=0, line_numbers=[], content=b"")
    errors = result["errors"]
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        errors.append(issue("invalid_encoding"))
        return result
    try:
        reader = csv.reader(
            io.StringIO(text, newline=""),
            delimiter="\t" if input_format == "tsv" else ",",
            strict=True,
        )
        headers = next(reader, [])
        if not headers or len(headers) > MAX_IMPORT_COLUMNS:
            errors.append(issue("empty_file" if not headers else "too_many_columns"))
            return result
        if any(not h.strip() for h in headers):
            errors.append(issue("blank_header", line_number=1))
        for header, count in Counter(headers).items():
            if count > 1:
                errors.append(issue("duplicate_header", header, line_number=1))
        rows = []
        while True:
            line = reader.line_num + 1
            row = next(reader, None)
            if row is None:
                break
            if not row:  # Match csv.DictReader's handling of truly empty lines.
                continue
            rows.append(row)
            result["line_numbers"].append(line)
            if len(row) != len(headers):
                errors.append(issue("row_width", row_number=len(rows), line_number=line))
            if len(rows) > MAX_IMPORT_ROWS:
                errors.append(issue("too_many_rows"))
                return result
    except csv.Error:
        errors.append(issue("invalid_csv"))
        return result
    result["row_count"] = len(rows)
    if not rows:
        errors.append(issue("empty_file"))
    if errors:
        return result
    fields = import_fields(schema)
    field_ids = {field["id"] for field in fields}
    targets = []
    for header in headers:
        if _is_record_path(header):
            targets.append(header.removeprefix("data."))
        elif _target_id(header) in field_ids:
            targets.append(f"var.{_target_id(header)}")
        else:
            targets.append(None)
            errors.append(issue("unknown_field", header, line_number=1))
    for target, count in Counter(t for t in targets if t is not None).items():
        if count > 1:
            errors.append(issue("duplicate_target", target, line_number=1))
    if errors:
        return result

    # Flag spreadsheet errors for review; never turn them into plausible observations.
    for number, row in enumerate(rows, 1):
        for index, value in enumerate(row):
            if value.strip() in EXCEL_ERRORS:
                errors.append(issue(
                    "spreadsheet_error", targets[index], number,
                    result["line_numbers"][number - 1],
                ))
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter="\t" if input_format == "tsv" else ",")
    writer.writerow(targets)
    writer.writerows(rows)
    result["content"] = output.getvalue().encode("utf-8")
    return result


def error_code(message: str) -> str:
    if message == "Field required":
        return "required"
    for substring, code in [
        ("Unknown variable field", "unknown_field"),
        ("valid integer", "integer"), ("valid boolean", "boolean"),
        ("valid number", "number"), ("valid string", "string"),
        ("match pattern", "pattern"), ("less than", "range"), ("greater than", "range"),
    ]:
        if substring in message:
            return code
    return "validation"


def format_errors(errors, line_numbers=()):
    result = []
    for error in errors:
        item = dict(error)
        item.setdefault("code", error_code(item.get("message", "")))
        row = item.get("row_number")
        if isinstance(row, int) and 0 < row <= len(line_numbers):
            item.setdefault("line_number", line_numbers[row - 1])
        result.append(item)
    return result


def preview_fingerprint(content, options, version, user_id):
    payload = dict(
        file_sha256=hashlib.sha256(content).hexdigest(), options=options,
        protocol_version_id=str(version.id), schema=version.json_schema, fields=version.fields,
        aimd=getattr(version, "aimd", ""), assigners=getattr(version, "assigners", {}),
        user_id=str(user_id),
    )
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def sign_preview(digest: str, secret: str) -> str:
    payload = f"{int(time.time()) + 1200}.{digest}"
    return f"{payload}.{hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()}"


def verify_preview(token: str, digest: str, secret: str) -> bool:
    try:
        expires, expected, signature = token.split(".")
        payload = f"{expires}.{expected}"
        actual = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return (
            int(expires) >= time.time()
            and hmac.compare_digest(expected, digest)
            and hmac.compare_digest(signature, actual)
        )
    except (ValueError, AttributeError, TypeError):
        return False
