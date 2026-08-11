"""Build the controlled quantity/provenance successor of the 2024/086 draft.

The builder is deliberately bound to three immutable artifacts.  It creates no
pricing result and its operator acknowledgement is not Human Approval.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "2024/086"
BASE_SCHEMA = "price_calculator_input_draft.v0.2"
CORRECTION_SCHEMA = "technical_csv_pr_section_composition_human_decisions.v0.1"
PARENT_SCHEMA = "technical_csv_label_human_review_packet.v0.5.1"
DECISION_ID = "IGOR-PR-SECTION-COMPOSITION-2024-086-001"
BASE_SHA256 = "571647f920f2ffcbfda66339c20be4673eb41127c0534054695c3d4cfc15fbf3"
CORRECTION_SHA256 = "12d6887edd44c3f13e5b7b5126a8441fa9a6aff350f7eae6ea81da7b4c1abc13"
PARENT_SHA256 = "1c68b9af8edfef2ca42f89c69e70a873553595d096413f197f9bfe77ec80fc00"
PROFILE = "controlled_quantity_correction_successor.v0.1"
QUANTITY_EFFECT = "QUANTITY_AND_PROVENANCE_CORRECTION"
PROVENANCE_EFFECT = "SECTION_PROVENANCE_RECONFIRMATION"
QUANTITY_ROW_IDS = (
    "ROW-DRAFT-0001",
    "ROW-DRAFT-0002",
    "ROW-DRAFT-0003",
    "ROW-DRAFT-0004",
    "ROW-DRAFT-0005",
    "ROW-DRAFT-0007",
    "ROW-DRAFT-0011",
    "ROW-DRAFT-0012",
    "ROW-DRAFT-0013",
    "ROW-DRAFT-0014",
)
PROVENANCE_ROW_IDS = (
    "ROW-DRAFT-0006",
    "ROW-DRAFT-0008",
    "ROW-DRAFT-0009",
    "ROW-DRAFT-0010",
    "ROW-DRAFT-0016",
    "ROW-DRAFT-0017",
    "ROW-DRAFT-0018",
    "ROW-DRAFT-0019",
)
AFFECTED_ROW_IDS = tuple(sorted((*QUANTITY_ROW_IDS, *PROVENANCE_ROW_IDS)))
EXPECTED_ROW_COUNT = 109
EXPECTED_CABINET_GROUP_COUNT = 14
EXPECTED_COMPONENT_GROUP_COUNT = 31


class SuccessorError(RuntimeError):
    """The controlled successor cannot be built or validated safely."""


def duplicate_key_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SuccessorError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def load_json(path: Path, description: str) -> tuple[dict[str, Any], bytes]:
    try:
        content = path.read_bytes()
        value = json.loads(content, object_pairs_hook=duplicate_key_guard)
    except SuccessorError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SuccessorError(f"{description} cannot be read: {exc}") from exc
    if not isinstance(value, dict):
        raise SuccessorError(f"{description} root must be an object")
    return value, content


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SuccessorError(f"{path} must be an object")
    return cast(Mapping[str, Any], value)


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise SuccessorError(f"{path} must be a list")
    return value


def require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SuccessorError(f"{path} must be a non-empty string")
    return value


def require_positive_number(value: Any, path: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise SuccessorError(f"{path} must be a positive number")
    return value


def require_external_path(value: Any, path: str) -> Path:
    result = Path(require_string(value, path)).expanduser().resolve(strict=False)
    if result.is_relative_to(PROJECT_ROOT):
        raise SuccessorError(f"{path} must reference an artifact outside Git")
    return result


def unique_index(
    values: Sequence[Any], key_name: str, path: str
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for position, raw_value in enumerate(values):
        value = require_mapping(raw_value, f"{path}[{position}]")
        key = require_string(value.get(key_name), f"{path}[{position}].{key_name}")
        if key in result:
            raise SuccessorError(f"duplicate {key_name}: {key}")
        result[key] = value
    return result


def draft_rows(draft: Mapping[str, Any]) -> list[Any]:
    calculator_format = require_mapping(
        draft.get("calculator_input_format"), "calculator_input_format"
    )
    return require_list(
        calculator_format.get("row_drafts"), "calculator_input_format.row_drafts"
    )


def row_id_sequence(draft: Mapping[str, Any], path: str) -> list[str]:
    result: list[str] = []
    for position, raw_row in enumerate(draft_rows(draft)):
        row = require_mapping(raw_row, f"{path}[{position}]")
        result.append(require_string(row.get("row_id"), f"{path}[{position}].row_id"))
    return result


def validate_base(base: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if (
        base.get("schema_version") != BASE_SCHEMA
        or base.get("draft_type") != "price_calculator_input_draft"
    ):
        raise SuccessorError("base draft contract mismatch")
    source = require_mapping(base.get("source"), "source")
    if source.get("project_id") != PROJECT_ID:
        raise SuccessorError("base draft project mismatch")
    cabinet_groups = require_list(base.get("cabinet_groups"), "cabinet_groups")
    if len(cabinet_groups) != EXPECTED_CABINET_GROUP_COUNT:
        raise SuccessorError("base cabinet-group coverage must be 14/14")
    rows = draft_rows(base)
    if len(rows) != EXPECTED_ROW_COUNT:
        raise SuccessorError("base row coverage must be 109/109")
    return unique_index(rows, "row_id", "calculator_input_format.row_drafts")


def validate_correction(
    correction: Mapping[str, Any],
) -> dict[str, tuple[int, Mapping[str, Any]]]:
    authority = require_mapping(correction.get("authority"), "authority")
    immutable = require_mapping(correction.get("immutable_state"), "immutable_state")
    boundary = require_mapping(
        correction.get("application_boundary"), "application_boundary"
    )
    if (
        correction.get("schema_version") != CORRECTION_SCHEMA
        or correction.get("project_id") != PROJECT_ID
        or correction.get("decision_id") != DECISION_ID
        or authority.get("authority") != "IGOR_DIRECT_HUMAN_APPROVAL"
        or authority.get("no_scope_expansion") is not True
        or immutable.get("immutable") is not True
        or immutable.get("no_overwrite") is not True
        or immutable.get("application_status") != "NOT_APPLIED"
        or boundary.get("corrections_applied") is not False
    ):
        raise SuccessorError("correction artifact contract mismatch")

    raw_corrections = require_list(
        correction.get("exact_row_corrections"), "exact_row_corrections"
    )
    if len(raw_corrections) != len(AFFECTED_ROW_IDS):
        raise SuccessorError("exact correction scope count must be 18")
    section_components: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for section_position, raw_section in enumerate(
        require_list(
            correction.get("exact_section_compositions"),
            "exact_section_compositions",
        )
    ):
        section = require_mapping(
            raw_section, f"exact_section_compositions[{section_position}]"
        )
        section_id = require_string(
            section.get("section"),
            f"exact_section_compositions[{section_position}].section",
        )
        for component_position, raw_component in enumerate(
            require_list(
                section.get("calculator_components"),
                f"exact_section_compositions[{section_position}].calculator_components",
            )
        ):
            component = require_mapping(
                raw_component,
                (
                    f"exact_section_compositions[{section_position}]"
                    f".calculator_components[{component_position}]"
                ),
            )
            row_id = require_string(
                component.get("row_draft_id"),
                f"section {section_id} calculator component row_draft_id",
            )
            if row_id in section_components:
                raise SuccessorError(f"duplicate section component row: {row_id}")
            section_components[row_id] = (section_id, component)
    if set(section_components) != set(AFFECTED_ROW_IDS):
        raise SuccessorError("exact section component scope must be the same 18 rows")

    result: dict[str, tuple[int, Mapping[str, Any]]] = {}
    for position, raw_correction in enumerate(raw_corrections):
        item = require_mapping(raw_correction, f"exact_row_corrections[{position}]")
        row_id = require_string(
            item.get("row_draft_id"),
            f"exact_row_corrections[{position}].row_draft_id",
        )
        if row_id in result:
            raise SuccessorError(f"duplicate exact correction scope: {row_id}")
        quantity_required = item.get("quantity_correction_required")
        effect = item.get("decision_effect")
        expected_required = row_id in QUANTITY_ROW_IDS
        expected_effect = QUANTITY_EFFECT if expected_required else PROVENANCE_EFFECT
        section_id, section_component = section_components.get(row_id, ("", {}))
        if (
            row_id not in AFFECTED_ROW_IDS
            or quantity_required is not expected_required
            or effect != expected_effect
            or item.get("decision_status") != "IGOR_CORRECTION_APPROVED_NOT_APPLIED"
            or item.get("section") != section_id
            or item.get("component_evidence_id")
            != section_component.get("component_evidence_id")
            or item.get("corrected_component_qty")
            != section_component.get("quantity_per_individual_cabinet")
        ):
            raise SuccessorError(f"misclassified exact correction scope: {row_id}")
        result[row_id] = (position, item)
    if set(result) != set(AFFECTED_ROW_IDS):
        raise SuccessorError("missing or extra exact correction scope")
    return result


def parent_component_membership(
    parent: Mapping[str, Any],
    *,
    correction_path: Path,
    corrections: Mapping[str, tuple[int, Mapping[str, Any]]],
) -> dict[str, Mapping[str, Any]]:
    if (
        parent.get("schema_version") != PARENT_SCHEMA
        or parent.get("project_id") != PROJECT_ID
    ):
        raise SuccessorError("parent packet contract mismatch")
    correction_summary = require_mapping(
        parent.get("pr_section_composition_correction"),
        "pr_section_composition_correction",
    )
    if (
        correction_summary.get("decision_id") != DECISION_ID
        or correction_summary.get("decision_artifact_path") != str(correction_path)
        or correction_summary.get("corrected_row_count") != 18
    ):
        raise SuccessorError("parent correction summary mismatch")
    lineage = require_mapping(parent.get("source_lineage"), "source_lineage")
    correction_lineage = require_mapping(
        lineage.get("pr_section_composition_human_decision"),
        "source_lineage.pr_section_composition_human_decision",
    )
    if (
        correction_lineage.get("path") != str(correction_path)
        or correction_lineage.get("sha256") != CORRECTION_SHA256
        or correction_lineage.get("schema_version") != CORRECTION_SCHEMA
        or correction_lineage.get("immutable") is not True
        or correction_lineage.get("application_status") != "NOT_APPLIED"
    ):
        raise SuccessorError("parent correction lineage mismatch")

    memberships: dict[str, Mapping[str, Any]] = {}
    groups = require_list(
        parent.get("component_label_review_groups"),
        "component_label_review_groups",
    )
    if len(groups) != EXPECTED_COMPONENT_GROUP_COUNT:
        raise SuccessorError("parent component-group coverage must be 31/31")
    for position, raw_group in enumerate(groups):
        group = require_mapping(raw_group, f"component_label_review_groups[{position}]")
        group_rows = require_list(
            group.get("row_draft_ids"),
            f"component_label_review_groups[{position}].row_draft_ids",
        )
        affected_group_rows = [
            require_string(row_id, "row_draft_ids[]")
            for row_id in group_rows
            if row_id in corrections
        ]
        if affected_group_rows:
            provenance = require_mapping(
                group.get("authoritative_correction_provenance"),
                (
                    f"component_label_review_groups[{position}]"
                    ".authoritative_correction_provenance"
                ),
            )
            expected_paths = [
                f"$.exact_row_corrections[{corrections[row_id][0]}]"
                for row_id in sorted(
                    affected_group_rows,
                    key=lambda row_id: corrections[row_id][0],
                )
            ]
            if (
                provenance.get("path") != str(correction_path)
                or provenance.get("sha256") != CORRECTION_SHA256
                or provenance.get("json_paths") != expected_paths
            ):
                raise SuccessorError(
                    "parent per-group correction provenance mismatch: "
                    f"component_label_review_groups[{position}]"
                )
        for raw_row_id in require_list(
            group_rows,
            f"component_label_review_groups[{position}].row_draft_ids",
        ):
            row_id = require_string(raw_row_id, "row_draft_ids[]")
            if row_id in memberships:
                raise SuccessorError(f"duplicate parent row membership: {row_id}")
            memberships[row_id] = group
    if len(memberships) != EXPECTED_ROW_COUNT:
        raise SuccessorError("parent row coverage must be 109/109")
    return memberships


def contains_hda_022(value: Any) -> bool:
    if isinstance(value, str):
        return "HDA-022" in value
    if isinstance(value, Mapping):
        return any(contains_hda_022(child) for child in value.values())
    if isinstance(value, list):
        return any(contains_hda_022(child) for child in value)
    return False


def source_quantity(correction: Mapping[str, Any], position: int) -> dict[str, Any]:
    return {
        "decision_id": DECISION_ID,
        "decision_kind": "DIRECT_COMPONENT_QUANTITY",
        "quantity_per_cabinet": correction["corrected_component_qty"],
        "decision_artifact_schema_version": CORRECTION_SCHEMA,
        "decision_artifact_sha256": CORRECTION_SHA256,
        "decision_json_path": f"$.exact_row_corrections[{position}]",
        "decision_effect": correction["decision_effect"],
        "quantity_correction_required": correction["quantity_correction_required"],
        "projection_status": "APPLIED_TO_SUCCESSOR_DRAFT_ONLY",
    }


def successor_metadata(
    *,
    base_path: Path,
    correction_path: Path,
    parent_path: Path,
    unchanged_row_ids: Sequence[str],
) -> dict[str, Any]:
    return {
        "profile": PROFILE,
        "base_draft": {
            "path": str(base_path),
            "sha256": BASE_SHA256,
            "schema_version": BASE_SCHEMA,
        },
        "authoritative_correction": {
            "path": str(correction_path),
            "sha256": CORRECTION_SHA256,
            "schema_version": CORRECTION_SCHEMA,
            "decision_id": DECISION_ID,
        },
        "authoritative_parent_packet": {
            "path": str(parent_path),
            "sha256": PARENT_SHA256,
            "schema_version": PARENT_SCHEMA,
        },
        "affected_row_count": 18,
        "quantity_corrected_row_count": 10,
        "provenance_reconfirmed_row_count": 8,
        "unchanged_row_count": 91,
        "quantity_corrected_row_ids": list(QUANTITY_ROW_IDS),
        "provenance_reconfirmed_row_ids": list(PROVENANCE_ROW_IDS),
        "unchanged_row_ids": list(unchanged_row_ids),
        "scope_expansion": False,
    }


def validate_parent_authority(
    *,
    row_id: str,
    base_row: Mapping[str, Any],
    correction: Mapping[str, Any],
    parent_group: Mapping[str, Any],
    base_position: int,
    correction_position: int,
) -> None:
    quantity_map = require_mapping(
        parent_group.get("row_component_qty_per_individual_cabinet"),
        f"{row_id}.row_component_qty_per_individual_cabinet",
    )
    corrected_quantity = require_positive_number(
        correction.get("corrected_component_qty"),
        f"{row_id}.corrected_component_qty",
    )
    current_quantity = require_positive_number(
        correction.get("current_pricing_component_qty"),
        f"{row_id}.current_pricing_component_qty",
    )
    base_values = require_mapping(
        base_row.get("calculator_values"), f"{row_id}.calculator_values"
    )
    old_source = require_mapping(
        base_row.get("source_quantity"), f"{row_id}.source_quantity"
    )
    old_decision_id = require_string(
        old_source.get("decision_id"), f"{row_id}.source_quantity.decision_id"
    )
    base_quantity = require_positive_number(
        base_values.get("component_qty"), f"{row_id}.base.component_qty"
    )
    evidence_ids = require_list(
        base_row.get("source_component_evidence_ids"),
        f"{row_id}.source_component_evidence_ids",
    )
    if len(evidence_ids) != 1:
        raise SuccessorError(f"base row must have one component evidence ID: {row_id}")
    evidence_id = require_string(
        evidence_ids[0], f"{row_id}.source_component_evidence_ids[0]"
    )
    parent_evidence_ids = require_list(
        parent_group.get("component_evidence_ids"),
        f"{row_id}.parent.component_evidence_ids",
    )
    source_paths = require_mapping(
        correction.get("source_paths"), f"{row_id}.correction.source_paths"
    )
    correction_json_path = f"$.exact_row_corrections[{correction_position}]"
    parent_provenance = require_mapping(
        parent_group.get("authoritative_correction_provenance"),
        f"{row_id}.authoritative_correction_provenance",
    )
    parent_scope = require_mapping(parent_group.get("scope"), f"{row_id}.parent.scope")
    parent_rows = require_list(
        parent_group.get("row_draft_ids"), f"{row_id}.parent.row_draft_ids"
    )
    if (
        base_values.get("component_qty") != current_quantity
        or correction.get("source_quantity_decision_id") != old_decision_id
        or quantity_map.get(row_id) != corrected_quantity
        or correction.get("component_evidence_id") != evidence_id
        or evidence_id not in parent_evidence_ids
        or correction.get("technical_signature") != base_row.get("approved_signature")
        or correction.get("technical_signature")
        != parent_group.get("technical_signature")
        or parent_group.get("mapping_request_id")
        != correction.get("mapping_request_id")
        or source_paths.get("pricing_row")
        != f"$.calculator_input_format.row_drafts[{base_position}]"
        or parent_group.get("quantity_decision_ids") != [DECISION_ID]
        or parent_provenance.get("path") is None
        or parent_provenance.get("sha256") != CORRECTION_SHA256
        or correction_json_path
        not in require_list(
            parent_provenance.get("json_paths"),
            f"{row_id}.authoritative_correction_provenance.json_paths",
        )
        or parent_scope.get("affected_rows_exact") != parent_rows
        or set(parent_rows) - set(AFFECTED_ROW_IDS)
        or parent_scope.get("section_provenance_verified") is not True
        or old_decision_id
        not in require_list(
            parent_group.get("superseded_quantity_decision_ids"),
            f"{row_id}.superseded_quantity_decision_ids",
        )
    ):
        raise SuccessorError(f"quantity/provenance authority mismatch: {row_id}")
    if row_id in QUANTITY_ROW_IDS:
        if (
            correction.get("superseded_quantity") != base_quantity
            or current_quantity != base_quantity
            or corrected_quantity == base_quantity
        ):
            raise SuccessorError(
                f"quantity correction superseded quantity mismatch: {row_id}"
            )
    elif (
        correction.get("superseded_quantity") is not None
        or current_quantity != base_quantity
        or corrected_quantity != base_quantity
    ):
        raise SuccessorError(f"provenance-only quantity semantics mismatch: {row_id}")
    if (row_id in PROVENANCE_ROW_IDS) != (current_quantity == corrected_quantity):
        raise SuccessorError(f"correction quantity classification mismatch: {row_id}")


def build_successor_payload(
    base: Mapping[str, Any],
    correction: Mapping[str, Any],
    parent: Mapping[str, Any],
    *,
    base_path: Path,
    correction_path: Path,
    parent_path: Path,
) -> dict[str, Any]:
    base_index = validate_base(base)
    base_positions = {
        row_id: position
        for position, row_id in enumerate(
            row_id_sequence(base, "calculator_input_format.row_drafts")
        )
    }
    corrections = validate_correction(correction)
    memberships = parent_component_membership(
        parent,
        correction_path=correction_path,
        corrections=corrections,
    )
    if set(base_index) != set(memberships):
        raise SuccessorError("base and parent row scopes differ")
    unchanged_ids = tuple(sorted(set(base_index) - set(AFFECTED_ROW_IDS)))
    if len(unchanged_ids) != 91:
        raise SuccessorError("unaffected row scope must be exactly 91")

    output = copy.deepcopy(dict(base))
    output_source = cast(
        dict[str, Any], require_mapping(output.get("source"), "source")
    )
    output_source["quantity_correction_successor"] = successor_metadata(
        base_path=base_path,
        correction_path=correction_path,
        parent_path=parent_path,
        unchanged_row_ids=unchanged_ids,
    )
    output_index = unique_index(
        draft_rows(output), "row_id", "calculator_input_format.row_drafts"
    )
    for row_id in AFFECTED_ROW_IDS:
        position, correction_item = corrections[row_id]
        validate_parent_authority(
            row_id=row_id,
            base_row=base_index[row_id],
            correction=correction_item,
            parent_group=memberships[row_id],
            base_position=base_positions[row_id],
            correction_position=position,
        )
        row = cast(dict[str, Any], output_index[row_id])
        if row_id in QUANTITY_ROW_IDS:
            values = cast(
                dict[str, Any],
                require_mapping(row.get("calculator_values"), "calculator_values"),
            )
            values["component_qty"] = correction_item["corrected_component_qty"]
        row["source_quantity"] = source_quantity(correction_item, position)

    validate_successor_payload(
        output,
        base,
        correction,
        parent,
        base_path=base_path,
        correction_path=correction_path,
        parent_path=parent_path,
    )
    return output


def validate_successor_payload(
    successor: Mapping[str, Any],
    base: Mapping[str, Any],
    correction: Mapping[str, Any],
    parent: Mapping[str, Any],
    *,
    base_path: Path,
    correction_path: Path,
    parent_path: Path,
) -> None:
    base_index = validate_base(base)
    base_order = row_id_sequence(base, "base.calculator_input_format.row_drafts")
    successor_order = row_id_sequence(
        successor, "successor.calculator_input_format.row_drafts"
    )
    if successor_order != base_order:
        raise SuccessorError("successor row order differs from immutable base draft")
    base_positions = {row_id: position for position, row_id in enumerate(base_order)}
    corrections = validate_correction(correction)
    memberships = parent_component_membership(
        parent,
        correction_path=correction_path,
        corrections=corrections,
    )
    successor_index = unique_index(
        draft_rows(successor), "row_id", "calculator_input_format.row_drafts"
    )
    if set(successor_index) != set(base_index) or set(base_index) != set(memberships):
        raise SuccessorError("successor row scope differs from base/parent")
    unchanged_ids = tuple(sorted(set(base_index) - set(AFFECTED_ROW_IDS)))

    expected_metadata = successor_metadata(
        base_path=base_path,
        correction_path=correction_path,
        parent_path=parent_path,
        unchanged_row_ids=unchanged_ids,
    )
    successor_source = require_mapping(successor.get("source"), "source")
    if successor_source.get("quantity_correction_successor") != expected_metadata:
        raise SuccessorError("successor metadata mismatch")
    expected_source = copy.deepcopy(dict(require_mapping(base.get("source"), "source")))
    expected_source["quantity_correction_successor"] = expected_metadata
    if successor_source != expected_source:
        raise SuccessorError("successor source changed outside controlled metadata")

    if successor.get("cabinet_groups") != base.get("cabinet_groups"):
        raise SuccessorError("all 14 cabinet groups must remain deep-equal")
    base_without_variable = copy.deepcopy(dict(base))
    successor_without_variable = copy.deepcopy(dict(successor))
    base_without_variable.pop("source", None)
    successor_without_variable.pop("source", None)
    base_format = cast(dict[str, Any], base_without_variable["calculator_input_format"])
    successor_format = cast(
        dict[str, Any], successor_without_variable["calculator_input_format"]
    )
    base_format.pop("row_drafts", None)
    successor_format.pop("row_drafts", None)
    if successor_without_variable != base_without_variable:
        raise SuccessorError("successor changed outside controlled source/rows")

    for row_id, base_row in base_index.items():
        actual_row = successor_index[row_id]
        if row_id not in AFFECTED_ROW_IDS:
            if actual_row != base_row:
                raise SuccessorError(f"unaffected row changed: {row_id}")
            continue
        position, correction_item = corrections[row_id]
        validate_parent_authority(
            row_id=row_id,
            base_row=base_row,
            correction=correction_item,
            parent_group=memberships[row_id],
            base_position=base_positions[row_id],
            correction_position=position,
        )
        expected_row = copy.deepcopy(dict(base_row))
        if row_id in QUANTITY_ROW_IDS:
            values = cast(dict[str, Any], expected_row["calculator_values"])
            values["component_qty"] = correction_item["corrected_component_qty"]
        expected_quantity_source = source_quantity(correction_item, position)
        expected_row["source_quantity"] = expected_quantity_source
        actual_quantity_source = require_mapping(
            actual_row.get("source_quantity"), f"{row_id}.source_quantity"
        )
        if contains_hda_022(actual_quantity_source):
            raise SuccessorError(
                f"superseded HDA-022 remains in affected row: {row_id}"
            )
        if actual_row != expected_row:
            raise SuccessorError(f"affected row changed outside exact scope: {row_id}")


def validate_embedded_successor(
    successor: Mapping[str, Any],
    *,
    expected_parent_path: Path | None = None,
    expected_parent_sha256: str | None = None,
) -> None:
    source = require_mapping(successor.get("source"), "source")
    metadata = require_mapping(
        source.get("quantity_correction_successor"),
        "source.quantity_correction_successor",
    )
    if metadata.get("profile") != PROFILE:
        raise SuccessorError("unsupported successor profile")
    base_meta = require_mapping(metadata.get("base_draft"), "base_draft")
    correction_meta = require_mapping(
        metadata.get("authoritative_correction"), "authoritative_correction"
    )
    parent_meta = require_mapping(
        metadata.get("authoritative_parent_packet"),
        "authoritative_parent_packet",
    )
    base_path = require_external_path(base_meta.get("path"), "base_draft.path")
    correction_path = require_external_path(
        correction_meta.get("path"), "authoritative_correction.path"
    )
    parent_path = require_external_path(
        parent_meta.get("path"), "authoritative_parent_packet.path"
    )
    bindings = (
        (base_meta, base_path, BASE_SHA256, BASE_SCHEMA, "base draft"),
        (
            correction_meta,
            correction_path,
            CORRECTION_SHA256,
            CORRECTION_SCHEMA,
            "correction artifact",
        ),
        (parent_meta, parent_path, PARENT_SHA256, PARENT_SCHEMA, "parent packet"),
    )
    loaded: list[dict[str, Any]] = []
    for item, path, digest, schema, description in bindings:
        if item.get("sha256") != digest or item.get("schema_version") != schema:
            raise SuccessorError(f"embedded {description} binding mismatch")
        data, content = load_json(path, description)
        if sha256_bytes(content) != digest:
            raise SuccessorError(f"{description} SHA-256 mismatch")
        loaded.append(data)
    if correction_meta.get("decision_id") != DECISION_ID:
        raise SuccessorError("embedded correction decision ID mismatch")
    if expected_parent_path is not None and parent_path != expected_parent_path:
        raise SuccessorError("application parent path differs from successor binding")
    if expected_parent_sha256 is not None and expected_parent_sha256 != PARENT_SHA256:
        raise SuccessorError("application parent SHA differs from successor binding")
    validate_successor_payload(
        successor,
        loaded[0],
        loaded[1],
        loaded[2],
        base_path=base_path,
        correction_path=correction_path,
        parent_path=parent_path,
    )
    for _item, path, digest, _schema, description in bindings:
        try:
            current_digest = sha256_bytes(path.read_bytes())
        except OSError as exc:
            raise SuccessorError(
                f"transitive {description} cannot be rechecked: {exc}"
            ) from exc
        if current_digest != digest:
            raise SuccessorError(f"transitive {description} changed during validation")


def publish_successor(
    *,
    base_json: Path,
    correction_json: Path,
    parent_packet_json: Path,
    output_json: Path,
    successor_build_authorized_by_igor: bool,
) -> dict[str, Any]:
    if not successor_build_authorized_by_igor:
        raise SuccessorError(
            "separate exact Igor successor-build authorization required"
        )
    output = output_json.expanduser().resolve(strict=False)
    if output.exists():
        raise SuccessorError("output JSON already exists; overwrite is forbidden")
    if output.is_relative_to(PROJECT_ROOT):
        raise SuccessorError("output JSON must be outside the Git project")
    if output.suffix.casefold() != ".json" or not output.parent.is_dir():
        raise SuccessorError("output JSON parent/suffix policy failed")

    paths = {
        "base": base_json.expanduser().resolve(strict=False),
        "correction": correction_json.expanduser().resolve(strict=False),
        "parent": parent_packet_json.expanduser().resolve(strict=False),
    }
    expected = {
        "base": BASE_SHA256,
        "correction": CORRECTION_SHA256,
        "parent": PARENT_SHA256,
    }
    loaded: dict[str, dict[str, Any]] = {}
    before_hashes: dict[str, str] = {}
    for role, path in paths.items():
        data, content = load_json(path, role)
        digest = sha256_bytes(content)
        if digest != expected[role]:
            raise SuccessorError(f"exact-bound SHA-256 mismatch: {role}")
        loaded[role] = data
        before_hashes[role] = digest
    payload = build_successor_payload(
        loaded["base"],
        loaded["correction"],
        loaded["parent"],
        base_path=paths["base"],
        correction_path=paths["correction"],
        parent_path=paths["parent"],
    )
    serialized = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
    staging_path: Path | None = None
    try:
        descriptor, staging_name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".staging", dir=output.parent
        )
        staging_path = Path(staging_name)
        with os.fdopen(descriptor, "wb") as staging_file:
            staging_file.write(serialized)
            staging_file.flush()
            os.fsync(staging_file.fileno())
        for role, path in paths.items():
            try:
                current_content = path.read_bytes()
            except OSError as exc:
                raise SuccessorError(
                    f"input cannot be rechecked during publication: {role}: {exc}"
                ) from exc
            if sha256_bytes(current_content) != before_hashes[role]:
                raise SuccessorError(f"input changed during successor build: {role}")
        try:
            os.link(staging_path, output)
        except FileExistsError as exc:
            raise SuccessorError(
                "output JSON appeared during publication; overwrite forbidden"
            ) from exc
        except OSError as exc:
            raise SuccessorError(f"exclusive atomic publication failed: {exc}") from exc
    finally:
        if staging_path is not None:
            staging_path.unlink(missing_ok=True)
    return payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-draft-json", required=True, type=Path)
    parser.add_argument("--correction-json", required=True, type=Path)
    parser.add_argument("--parent-packet-json", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument(
        "--successor-build-authorized-by-igor",
        action="store_true",
        help="Operator acknowledgement; the flag itself is not Human Approval.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        publish_successor(
            base_json=args.base_draft_json,
            correction_json=args.correction_json,
            parent_packet_json=args.parent_packet_json,
            output_json=args.output_json,
            successor_build_authorized_by_igor=(
                args.successor_build_authorized_by_igor
            ),
        )
    except SuccessorError as exc:
        print(f"FAIL: {exc}")
        return 1
    print("PASS: controlled v0.2 successor draft created; pricing not executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
