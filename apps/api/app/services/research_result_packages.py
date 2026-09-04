"""Final Research Result Package validation, sealing, and portable rendering."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi.encoders import jsonable_encoder

from app.services.research_runtime import canonical_digest

RESULT_PACKAGE_SCHEMA = "airalogy.research-result-package.v1"
LIST_FIELDS = (
    "success_criteria",
    "claims",
    "evidence",
    "data_assets",
    "knowledge_items",
    "protocol_improvements",
    "actions",
    "failed_attempts",
    "unresolved_questions",
)


class ResearchResultPackageError(ValueError):
    pass


def normalize_final_result_package(package: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe complete package or fail closed."""

    normalized = jsonable_encoder(package)
    if normalized.get("schema") != RESULT_PACKAGE_SCHEMA:
        raise ResearchResultPackageError("Unsupported Research Result Package schema")
    for field in ("task_id", "run_id", "goal"):
        if not str(normalized.get(field) or "").strip():
            raise ResearchResultPackageError(
                f"Research Result Package is missing {field}"
            )
    for field in LIST_FIELDS:
        if not isinstance(normalized.get(field), list):
            raise ResearchResultPackageError(
                f"Research Result Package {field} must be a list"
            )
    for field in ("reproducibility", "budget"):
        if not isinstance(normalized.get(field), dict):
            raise ResearchResultPackageError(
                f"Research Result Package {field} must be an object"
            )
    if not str(normalized.get("reviewed_conclusion") or "").strip():
        raise ResearchResultPackageError(
            "Research Result Package requires a reviewed conclusion"
        )
    if not str(normalized.get("reviewed_by_user_id") or "").strip():
        raise ResearchResultPackageError(
            "Research Result Package requires a human reviewer"
        )
    if not str(normalized.get("reviewed_at") or "").strip():
        raise ResearchResultPackageError(
            "Research Result Package requires a review time"
        )
    return normalized


def result_package_digest(package: dict[str, Any]) -> str:
    return canonical_digest(jsonable_encoder(package))


def verify_result_package_digest(package: dict[str, Any], digest: str) -> None:
    if result_package_digest(package) != digest:
        raise ResearchResultPackageError(
            "Research Result Package snapshot digest does not match its content"
        )


def _inline(value: Any, fallback: str = "-") -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return text or fallback


def _records(value: Any) -> list[dict[str, Any]]:
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _json_block(value: Any) -> str:
    payload = json.dumps(
        jsonable_encoder(value), ensure_ascii=False, indent=2, sort_keys=True
    )
    fence = "````" if "```" in payload else "```"
    return f"{fence}json\n{payload}\n{fence}"


def render_result_package_markdown(
    *,
    task_title: str,
    run_number: int,
    package: dict[str, Any],
    digest: str,
    sealed: bool,
    finalized_at: str | None,
    language: Literal["en", "zh"] = "en",
) -> str:
    labels = {
        "en": {
            "title": "Research Result Package",
            "run": "Run",
            "sealed": "Human-finalized immutable snapshot",
            "legacy": "Unsealed legacy package",
            "digest": "SHA-256 package digest",
            "finalized": "Finalized at",
            "goal": "Research goal",
            "criteria": "Success criteria",
            "assessment": "Human assessment",
            "conclusion": "Reviewed conclusion",
            "claims": "Claims",
            "evidence": "Evidence",
            "data": "Data assets",
            "knowledge": "Knowledge outputs",
            "improvements": "Protocol improvements",
            "execution": "Execution trail",
            "failed": "Failed attempts",
            "questions": "Unresolved questions",
            "reproducibility": "Reproducibility snapshot",
            "budget": "Budget",
            "empty": "None recorded.",
            "raw": "Complete machine-readable snapshot",
        },
        "zh": {
            "title": "科研结果包",
            "run": "Run",
            "sealed": "经人工定稿的不可变快照",
            "legacy": "未封存的历史结果包",
            "digest": "结果包 SHA-256 摘要",
            "finalized": "定稿时间",
            "goal": "科研目标",
            "criteria": "成功标准",
            "assessment": "人工评估",
            "conclusion": "审核结论",
            "claims": "科学主张",
            "evidence": "证据",
            "data": "数据资产",
            "knowledge": "知识成果",
            "improvements": "Protocol 改进",
            "execution": "执行轨迹",
            "failed": "失败尝试",
            "questions": "未解决问题",
            "reproducibility": "复现快照",
            "budget": "预算",
            "empty": "无记录。",
            "raw": "完整机器可读快照",
        },
    }[language]
    lines = [
        f"# {labels['title']}: {_inline(task_title)}",
        "",
        f"- {labels['run']}: {run_number}",
        f"- {labels['digest']}: `{digest}`",
        f"- {labels['finalized']}: {_inline(finalized_at)}",
        f"- {labels['sealed'] if sealed else labels['legacy']}",
        "",
        f"## {labels['goal']}",
        "",
        str(package.get("goal") or labels["empty"]).strip(),
        "",
        f"## {labels['criteria']}",
        "",
    ]
    criteria = _strings(package.get("success_criteria"))
    lines.extend([f"- {_inline(item)}" for item in criteria] or [labels["empty"]])
    lines.extend(
        [
            "",
            f"## {labels['assessment']}",
            "",
            f"- goal_assessment: `{_inline(package.get('goal_assessment'))}`",
            f"- scientific_outcome: `{_inline(package.get('scientific_outcome'))}`",
            "",
            f"## {labels['conclusion']}",
            "",
            str(
                package.get("reviewed_conclusion")
                or package.get("narrative_conclusion")
                or labels["empty"]
            ).strip(),
            "",
        ]
    )

    sections = (
        ("claims", "statement", ("state", "confidence", "uncertainty")),
        (
            "evidence",
            "summary",
            (
                "kind",
                "quality_state",
                "artifact_type",
                "artifact_id",
                "artifact_version",
            ),
        ),
        ("data", "name", ("kind", "status", "current_version", "id")),
        ("knowledge", "title", ("kind", "state", "revision", "id")),
        ("improvements", "summary", ("state", "base_protocol_version", "id")),
        ("execution", "title", ("sequence", "kind", "status", "id", "error")),
    )
    field_by_section = {
        "claims": "claims",
        "evidence": "evidence",
        "data": "data_assets",
        "knowledge": "knowledge_items",
        "improvements": "protocol_improvements",
        "execution": "actions",
    }
    for section, primary, details in sections:
        lines.extend([f"## {labels[section]}", ""])
        records = _records(package.get(field_by_section[section]))
        if not records:
            lines.extend([labels["empty"], ""])
            continue
        for index, record in enumerate(records, start=1):
            headline = record.get(primary) or record.get("id") or f"#{index}"
            lines.append(f"{index}. **{_inline(headline)}**")
            detail = "; ".join(
                f"{field}={_inline(record.get(field))}"
                for field in details
                if record.get(field) not in (None, "", [])
            )
            if detail:
                lines.append(f"   - {detail}")
        lines.append("")

    for key in ("failed", "questions"):
        source = "failed_attempts" if key == "failed" else "unresolved_questions"
        lines.extend([f"## {labels[key]}", ""])
        values = _strings(package.get(source))
        lines.extend([f"- {_inline(item)}" for item in values] or [labels["empty"]])
        lines.append("")

    lines.extend(
        [
            f"## {labels['reproducibility']}",
            "",
            _json_block(package.get("reproducibility") or {}),
            "",
            f"## {labels['budget']}",
            "",
            _json_block(package.get("budget") or {}),
            "",
            f"## {labels['raw']}",
            "",
            _json_block(package),
            "",
        ]
    )
    return "\n".join(lines)
