from __future__ import annotations

from typing import Any


SCHEMA_GROUPS: dict[str, dict[str, Any]] = {
    "analytic_method": {
        "label": "Analytic method",
        "definition": (
            "Methods, modeling strategies, and measurement strategies that operate as "
            "analytic or inferential machinery in computational social science."
        ),
        "member_types": ["method", "modeling_strategy", "measurement_strategy"],
    },
    "evidence_and_infrastructure": {
        "label": "Evidence and infrastructure",
        "definition": (
            "Data sources, platforms, software, APIs, and other infrastructure used to "
            "collect, process, or host empirical evidence."
        ),
        "member_types": ["data_source", "infrastructure_tooling"],
    },
    "validation_and_governance": {
        "label": "Validation and governance",
        "definition": (
            "Evaluation protocols, reproducibility practices, access rules, ethics, "
            "privacy, and other governance practices around empirical workflows."
        ),
        "member_types": ["evaluation_protocol", "governance_practice"],
    },
}

SCHEMA_GROUP_BY_TYPE: dict[str, str] = {
    entity_type: group
    for group, spec in SCHEMA_GROUPS.items()
    for entity_type in spec["member_types"]
}


def schema_group_for_type(entity_type: str | None) -> str:
    value = str(entity_type or "unknown").strip() or "unknown"
    return SCHEMA_GROUP_BY_TYPE.get(value, value)


def schema_group_label(schema_group: str | None) -> str:
    value = str(schema_group or "unknown").strip() or "unknown"
    return str((SCHEMA_GROUPS.get(value) or {}).get("label") or value)


def schema_group_definition(schema_group: str | None) -> str:
    value = str(schema_group or "unknown").strip() or "unknown"
    return str((SCHEMA_GROUPS.get(value) or {}).get("definition") or "")


def schema_group_members(schema_group: str | None) -> list[str]:
    value = str(schema_group or "unknown").strip() or "unknown"
    members = (SCHEMA_GROUPS.get(value) or {}).get("member_types") or []
    return [str(item) for item in members]


def schema_group_records(entity_schema: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    entity_schema = entity_schema or {}
    rows: list[dict[str, Any]] = []
    for group, spec in sorted(SCHEMA_GROUPS.items()):
        members = schema_group_members(group)
        member_labels = []
        for member in members:
            member_spec = entity_schema.get(member) if isinstance(entity_schema, dict) else {}
            member_labels.append(str((member_spec or {}).get("label") or member))
        rows.append(
            {
                "schema_group": group,
                "label": schema_group_label(group),
                "definition": schema_group_definition(group),
                "member_types": members,
                "member_type_labels": member_labels,
            }
        )
    return rows
