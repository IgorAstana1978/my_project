"""Apply approved technical decisions to a v0.2 pricing-input draft.

This path only completes technical calculator inputs.  It does not calculate
prices and its CLI acknowledgement does not create Human Approval.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "price_calculator_input_draft.v0.2"
EFFECTIVE_PACKET_SCHEMA = "technical_csv_label_human_review_packet.v0.6"
PRODUCT_DECISION_SCHEMA = "technical_sche_product_name_human_decisions.v0.1"
AD12_DECISION_SCHEMA = "technical_ad12_breaking_capacity_human_decisions.v0.1"
AD12_COMPONENT_CODE = "EKF-AD12-1P-N-C16-30MA-4P5KA"
AD12_INSTALL_TYPE = "diff_1p_n"
AD12_MAPPING_IDS = {"COMPONENT-MAPPING-009", "COMPONENT-MAPPING-016"}
COMPLETED_MAPPING_STATUS = "APPROVED_HUMAN_DECISIONS_APPLIED"
COMPLETION_STATUS = "V02_TECHNICAL_COMPLETION_APPLIED_NOT_PRICED"
CALCULATOR_COLUMNS = (
    "product_name",
    "cabinet_code",
    "consumables_factor",
    "component_code",
    "component_qty",
    "install_type",
)
EXPECTED_COMPONENT_GROUPS = 31
EXPECTED_ROW_COUNT = 109
EXPECTED_CABINET_GROUPS = 14


class CompletionError(RuntimeError):
    """The v0.2 completion overlay cannot proceed safely."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft-json", required=True, type=Path)
    parser.add_argument("--expected-draft-sha256", required=True)
    parser.add_argument("--effective-packet-json", required=True, type=Path)
    parser.add_argument("--expected-effective-packet-sha256", required=True)
    parser.add_argument("--sche-product-name-decisions-json", required=True, type=Path)
    parser.add_argument("--expected-sche-product-name-decisions-sha256", required=True)
    parser.add_argument(
        "--ad12-breaking-capacity-decisions-json", required=True, type=Path
    )
    parser.add_argument(
        "--expected-ad12-breaking-capacity-decisions-sha256", required=True
    )
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument(
        "--application-authorized-by-igor",
        action="store_true",
        help=(
            "Operator acknowledgement of a separate exact Human Authorization. "
            "The flag itself is not Human Approval."
        ),
    )
    return parser.parse_args(argv)


def duplicate_key_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise CompletionError(f"duplicate JSON key is forbidden: {key}")
        value[key] = child
    return value


def load_json(path: Path, description: str) -> tuple[dict[str, Any], bytes]:
    try:
        content = path.read_bytes()
        value = json.loads(content, object_pairs_hook=duplicate_key_guard)
    except CompletionError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompletionError(f"{description} cannot be read: {exc}") from exc
    if not isinstance(value, dict):
        raise CompletionError(f"{description} root must be an object")
    return value, content


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def require_sha256(value: str, path: str) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise CompletionError(f"{path} must be exactly 64 lowercase hex characters")
    return value


def require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CompletionError(f"{path} must be an object")
    return cast(Mapping[str, Any], value)


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise CompletionError(f"{path} must be a list")
    return value


def require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompletionError(f"{path} must be a non-empty string")
    return value


def require_positive_number(value: Any, path: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise CompletionError(f"{path} must be a positive number")
    return value


def resolved_external_path(value: Any, path: str) -> Path:
    source_path = Path(require_string(value, path)).expanduser().resolve(strict=False)
    if source_path.is_relative_to(PROJECT_ROOT):
        raise CompletionError(
            f"{path} must reference an immutable artifact outside Git"
        )
    return source_path


def verify_packet_contract(effective: Mapping[str, Any]) -> None:
    if (
        effective.get("schema_version") != EFFECTIVE_PACKET_SCHEMA
        or effective.get("project_id") != "2024/086"
        or effective.get("status") != "IGOR_FINAL_HUMAN_REVIEW_COMPLETE_NOT_APPLIED"
    ):
        raise CompletionError("effective packet contract mismatch")
    counts = require_mapping(
        effective.get("effective_human_review_counts"),
        "effective_human_review_counts",
    )
    if any(
        counts.get(field_name) != 0
        for field_name in (
            "breaking_capacity_remaining",
            "component_label_remaining",
            "cabinet_label_remaining",
            "technical_conflict_remaining",
            "total_remaining_human_review",
        )
    ):
        raise CompletionError("effective Human Review is not complete")
    invariants = require_mapping(effective.get("invariants"), "invariants")
    if (
        invariants.get("component_groups") != EXPECTED_COMPONENT_GROUPS
        or invariants.get("component_coverage") != "109/109"
        or invariants.get("cabinet_coverage") != "14/14"
        or invariants.get("scope_expansion") is not False
    ):
        raise CompletionError("effective packet coverage invariants mismatch")


def load_parent_scope_packet(
    effective: Mapping[str, Any],
) -> tuple[dict[str, Any], str, Path]:
    lineage = require_mapping(effective.get("source_lineage"), "source_lineage")
    parent = require_mapping(
        lineage.get("parent_effective_packet"),
        "source_lineage.parent_effective_packet",
    )
    parent_path = resolved_external_path(
        parent.get("path"),
        "source_lineage.parent_effective_packet.path",
    )
    expected_sha = require_string(
        parent.get("sha256"),
        "source_lineage.parent_effective_packet.sha256",
    )
    parent_data, parent_bytes = load_json(parent_path, "parent scope packet")
    actual_sha = sha256_bytes(parent_bytes)
    if actual_sha != expected_sha:
        raise CompletionError("parent scope packet SHA-256 mismatch")
    return parent_data, actual_sha, parent_path


def unique_index(
    values: Sequence[Any],
    key_name: str,
    path: str,
) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    for position, raw_value in enumerate(values):
        value = require_mapping(raw_value, f"{path}[{position}]")
        key = require_string(value.get(key_name), f"{path}[{position}].{key_name}")
        if key in index:
            raise CompletionError(f"duplicate {key_name}: {key}")
        index[key] = value
    return index


def exact_row_membership(
    groups: Sequence[Mapping[str, Any]],
    row_field: str,
    path: str,
) -> dict[str, Mapping[str, Any]]:
    memberships: dict[str, Mapping[str, Any]] = {}
    for group in groups:
        for raw_row_id in require_list(group.get(row_field), f"{path}.{row_field}"):
            row_id = require_string(raw_row_id, f"{path}.{row_field}[]")
            if row_id in memberships:
                raise CompletionError(f"duplicate row membership: {row_id}")
            memberships[row_id] = group
    return memberships


def breaking_capacity_by_review_group(
    effective: Mapping[str, Any],
) -> dict[str, str]:
    resolved = require_mapping(
        effective.get("resolved_human_review_not_applied"),
        "resolved_human_review_not_applied",
    )
    decisions = require_list(
        resolved.get("breaking_capacity_decisions"),
        "resolved_human_review_not_applied.breaking_capacity_decisions",
    )
    result: dict[str, str] = {}
    for raw_decision in decisions:
        decision = require_mapping(raw_decision, "breaking capacity decision")
        scope = require_mapping(decision.get("question_scope"), "question_scope")
        answer = require_mapping(decision.get("decision"), "decision")
        review_group_id = require_string(
            scope.get("review_group_id"),
            "question_scope.review_group_id",
        )
        value = require_string(
            answer.get("breaking_capacity"),
            "decision.breaking_capacity",
        )
        if (
            answer.get("status") != "APPROVED_BY_IGOR_NOT_APPLIED"
            or answer.get("scope_expansion") is not False
            or review_group_id in result
        ):
            raise CompletionError("invalid or duplicate breaking-capacity decision")
        result[review_group_id] = value
    if len(result) != 18:
        raise CompletionError("breaking-capacity decision coverage must be 18/18")
    return result


def validate_ad12_decisions(
    artifact: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    if (
        artifact.get("schema") != AD12_DECISION_SCHEMA
        or artifact.get("status")
        != "IGOR_AD12_45KA_EXACT_REPLACEMENT_APPROVED_NOT_APPLIED"
    ):
        raise CompletionError("AD12 Human Decision contract mismatch")
    result: dict[str, Mapping[str, Any]] = {}
    for raw_decision in require_list(artifact.get("decisions"), "AD12 decisions"):
        decision = require_mapping(raw_decision, "AD12 decision")
        scope = require_mapping(decision.get("exact_scope"), "AD12 exact_scope")
        mapping_id = require_string(
            scope.get("mapping_request_id"),
            "AD12 exact_scope.mapping_request_id",
        )
        state = require_mapping(
            decision.get("approved_replacement_state"),
            "AD12 approved_replacement_state",
        )
        if (
            mapping_id not in AD12_MAPPING_IDS
            or mapping_id in result
            or state.get("manufacturer_article") != "DA12-16-30-bas"
            or state.get("characteristic") != "C"
            or state.get("breaking_capacity") != "4,5кА"
            or decision.get("scope_expansion") is not False
            or decision.get("application_status") != "NOT_APPLIED"
        ):
            raise CompletionError("AD12 scoped decision mismatch")
        result[mapping_id] = decision
    if set(result) != AD12_MAPPING_IDS:
        raise CompletionError("AD12 scoped decision coverage mismatch")
    return result


def validate_product_name_decisions(
    artifact: Mapping[str, Any],
) -> dict[str, str]:
    if (
        artifact.get("schema") != PRODUCT_DECISION_SCHEMA
        or artifact.get("status") != "IGOR_SCHE_PRODUCT_NAMES_APPROVED_NOT_APPLIED"
    ):
        raise CompletionError("ЩЭ product-name Human Decision contract mismatch")
    expected = {
        "CABINET-GROUP-010": "ЩЭ-3кв",
        "CABINET-GROUP-011": "ЩЭ-4кв",
        "CABINET-GROUP-012": "ЩЭ-5кв",
        "CABINET-GROUP-013": "ЩЭ-6кв",
    }
    result: dict[str, str] = {}
    for raw_decision in require_list(artifact.get("decisions"), "product decisions"):
        decision = require_mapping(raw_decision, "product decision")
        scope = require_mapping(decision.get("exact_scope"), "product exact_scope")
        group_id = require_string(
            scope.get("cabinet_group_id"),
            "product exact_scope.cabinet_group_id",
        )
        product_name = require_string(
            decision.get("approved_product_name"),
            "approved_product_name",
        )
        if (
            expected.get(group_id) != product_name
            or group_id in result
            or decision.get("scope_expansion") is not False
            or decision.get("application_status") != "NOT_APPLIED"
        ):
            raise CompletionError("ЩЭ product-name scoped decision mismatch")
        result[group_id] = product_name
    if result != expected:
        raise CompletionError("ЩЭ product-name decision coverage mismatch")
    return result


def approved_cabinet_fields(
    effective: Mapping[str, Any],
) -> dict[str, tuple[str, str]]:
    resolved = require_mapping(
        effective.get("resolved_human_review_not_applied"),
        "resolved_human_review_not_applied",
    )
    decisions = require_list(
        resolved.get("cabinet_label_decisions"),
        "resolved_human_review_not_applied.cabinet_label_decisions",
    )
    result: dict[str, tuple[str, str]] = {}
    for raw_decision in decisions:
        decision = require_mapping(raw_decision, "cabinet label decision")
        scope = require_mapping(
            decision.get("question_scope"), "cabinet question_scope"
        )
        answer = require_mapping(decision.get("decision"), "cabinet decision")
        code = require_string(
            scope.get("internal_cabinet_code"),
            "question_scope.internal_cabinet_code",
        )
        label = require_string(
            scope.get("proposed_authoritative_label"),
            "question_scope.proposed_authoritative_label",
        )
        if (
            answer.get("status") != "APPROVED_BY_IGOR_NOT_APPLIED"
            or answer.get("scope_expansion") is not False
        ):
            raise CompletionError("cabinet label decision is not approved")
        for raw_group_id in require_list(
            scope.get("cabinet_group_ids"),
            "question_scope.cabinet_group_ids",
        ):
            group_id = require_string(raw_group_id, "cabinet_group_ids[]")
            if group_id in result:
                raise CompletionError(
                    f"duplicate cabinet decision membership: {group_id}"
                )
            result[group_id] = (code, label)
    if len(result) != EXPECTED_CABINET_GROUPS:
        raise CompletionError("cabinet decision coverage must be 14/14")
    return result


def has_curve_c(label: str) -> bool:
    return re.search(r"(?:\b|\()(?:c|с)(?=\d|\)|\b)", label.casefold()) is not None


def final_component_label(base_label: str, breaking_capacity: str | None) -> str:
    label = base_label.strip()
    if breaking_capacity is None:
        return label
    label = label.rstrip(" ,.;")
    if not has_curve_c(label):
        label = f"{label}, C"
    return f"{label}, {breaking_capacity}"


def complete_v02_payload(
    draft: Mapping[str, Any],
    effective: Mapping[str, Any],
    product_decisions: Mapping[str, Any],
    ad12_decisions: Mapping[str, Any],
    *,
    lineage: Mapping[str, Mapping[str, str]],
    applied_at_utc: str,
) -> dict[str, Any]:
    if (
        draft.get("schema_version") != SCHEMA_VERSION
        or draft.get("draft_type") != "price_calculator_input_draft"
    ):
        raise CompletionError("input draft must be price_calculator_input_draft.v0.2")
    verify_packet_contract(effective)
    parent, parent_sha, parent_path = load_parent_scope_packet(effective)
    component_groups = [
        require_mapping(value, "component_label_review_groups[]")
        for value in require_list(
            parent.get("component_label_review_groups"),
            "component_label_review_groups",
        )
    ]
    cabinet_groups = [
        require_mapping(value, "cabinet_label_review_groups[]")
        for value in require_list(
            parent.get("cabinet_label_review_groups"),
            "cabinet_label_review_groups",
        )
    ]
    if (
        len(component_groups) != EXPECTED_COMPONENT_GROUPS
        or len(cabinet_groups) != EXPECTED_CABINET_GROUPS
    ):
        raise CompletionError("parent scope group counts mismatch")
    component_membership = exact_row_membership(
        component_groups,
        "row_draft_ids",
        "component_label_review_groups",
    )
    cabinet_membership = exact_row_membership(
        cabinet_groups,
        "affected_row_draft_ids",
        "cabinet_label_review_groups",
    )
    if len(component_membership) != EXPECTED_ROW_COUNT or set(
        component_membership
    ) != set(cabinet_membership):
        raise CompletionError("parent row coverage must be exact 109/109")

    bc_by_group = breaking_capacity_by_review_group(effective)
    ad12_by_mapping = validate_ad12_decisions(ad12_decisions)
    product_by_group = validate_product_name_decisions(product_decisions)
    cabinet_fields = approved_cabinet_fields(effective)

    output = copy.deepcopy(dict(draft))
    raw_output_groups = require_list(output.get("cabinet_groups"), "cabinet_groups")
    output_groups = unique_index(
        raw_output_groups, "cabinet_group_id", "cabinet_groups"
    )
    parent_cabinet_index = unique_index(
        cabinet_groups,
        "cabinet_group_id",
        "parent cabinet groups",
    )
    if set(output_groups) != set(parent_cabinet_index):
        raise CompletionError("draft cabinet scope differs from approved 14 groups")

    for group_id, raw_group in output_groups.items():
        group = cast(dict[str, Any], raw_group)
        parent_group = parent_cabinet_index[group_id]
        approved_code, approved_label = cabinet_fields[group_id]
        expected_rows = require_list(
            parent_group.get("affected_row_draft_ids"),
            f"{group_id}.affected_row_draft_ids",
        )
        if group.get("row_draft_ids") != expected_rows:
            raise CompletionError(f"draft cabinet row scope mismatch: {group_id}")
        source_template = require_string(
            parent_group.get("source_cabinet_template"),
            f"{group_id}.source_cabinet_template",
        )
        if group.get("source_cabinet_template") != source_template:
            raise CompletionError(f"draft cabinet template mismatch: {group_id}")
        if group_id in product_by_group:
            product_name = product_by_group[group_id]
        else:
            product_name = require_string(
                group.get("product_name"), f"{group_id}.product_name"
            )
        group["product_name"] = product_name
        group["cabinet_code"] = approved_code
        group["cabinet_label"] = approved_label
        group["consumables_factor"] = require_positive_number(
            parent_group.get("consumables_factor"),
            f"{group_id}.consumables_factor",
        )
        group["mapping_status"] = COMPLETED_MAPPING_STATUS

    calculator_format = require_mapping(
        output.get("calculator_input_format"),
        "calculator_input_format",
    )
    if (
        calculator_format.get("kind") != "confirmed_composition_csv_row_drafts"
        or calculator_format.get("delimiter") != ";"
        or calculator_format.get("columns") != list(CALCULATOR_COLUMNS)
    ):
        raise CompletionError("draft calculator format constants mismatch")
    raw_rows = require_list(
        calculator_format.get("row_drafts"),
        "calculator_input_format.row_drafts",
    )
    row_index = unique_index(raw_rows, "row_id", "calculator_input_format.row_drafts")
    if set(row_index) != set(component_membership):
        raise CompletionError("draft row scope differs from approved 109 rows")

    for row_id, raw_row in row_index.items():
        row = cast(dict[str, Any], raw_row)
        component_group = component_membership[row_id]
        cabinet_group = cabinet_membership[row_id]
        cabinet_group_id = require_string(
            cabinet_group.get("cabinet_group_id"),
            f"{row_id}.cabinet_group_id",
        )
        if row.get("cabinet_group_id") != cabinet_group_id:
            raise CompletionError(f"draft row cabinet membership mismatch: {row_id}")
        quantity_map = require_mapping(
            component_group.get("row_component_qty_per_individual_cabinet"),
            f"{row_id}.row_component_qty_per_individual_cabinet",
        )
        expected_quantity = require_positive_number(
            quantity_map.get(row_id),
            f"{row_id}.component_qty",
        )
        values = cast(
            dict[str, Any],
            require_mapping(
                row.get("calculator_values"), f"{row_id}.calculator_values"
            ),
        )
        if values.get("component_qty") != expected_quantity:
            raise CompletionError(f"draft quantity changed for {row_id}")

        review_group_id = require_string(
            component_group.get("review_group_id"),
            f"{row_id}.review_group_id",
        )
        mapping_id = require_string(
            component_group.get("mapping_request_id"),
            f"{row_id}.mapping_request_id",
        )
        component_code = component_group.get("approved_internal_component_code")
        install_type = component_group.get("install_type")
        breaking_capacity = bc_by_group.get(review_group_id)
        if (
            breaking_capacity is None
            and component_group.get("breaking_capacity_policy_applies") is True
        ):
            approved_capacity = component_group.get("breaking_capacity_human_approval")
            if isinstance(approved_capacity, str) and approved_capacity:
                breaking_capacity = approved_capacity
        if mapping_id in AD12_MAPPING_IDS:
            decision = ad12_by_mapping[mapping_id]
            exact_scope = require_mapping(
                decision.get("exact_scope"), "AD12 exact_scope"
            )
            exact_rows = set(
                require_list(exact_scope.get("row_draft_ids"), "AD12 exact rows")
            )
            if set(component_group.get("row_draft_ids", [])) != exact_rows:
                raise CompletionError(f"AD12 exact scope mismatch: {mapping_id}")
            component_code = AD12_COMPONENT_CODE
            install_type = AD12_INSTALL_TYPE
            breaking_capacity = "4,5кА"
        if not isinstance(component_code, str) or not component_code:
            raise CompletionError(f"component_code is unresolved for {review_group_id}")
        if not isinstance(install_type, str) or not install_type:
            raise CompletionError(f"install_type is unresolved for {review_group_id}")

        base_label = (
            component_group.get("approved_authoritative_component_label")
            or component_group.get("proposed_base_label_without_breaking_capacity")
            or component_group.get("proposed_authoritative_component_label")
        )
        base_label = require_string(base_label, f"{review_group_id}.base_label")
        label = final_component_label(base_label, breaking_capacity)
        completed_group = output_groups[cabinet_group_id]
        values.update(
            {
                "product_name": completed_group["product_name"],
                "cabinet_code": completed_group["cabinet_code"],
                "consumables_factor": completed_group["consumables_factor"],
                "component_code": component_code,
                "install_type": install_type,
            }
        )
        row["component_label"] = label
        row["mapping_status"] = COMPLETED_MAPPING_STATUS

    coverage = require_mapping(output.get("coverage"), "coverage")
    if (
        coverage.get("pricing_row_draft_count") != EXPECTED_ROW_COUNT
        or coverage.get("cabinet_group_count") != EXPECTED_CABINET_GROUPS
    ):
        raise CompletionError("draft coverage fields mismatch")
    output["completion"] = {
        "status": COMPLETION_STATUS,
        "applied_at_utc": applied_at_utc,
        "application_authorization_claim": (
            "SEPARATE_EXACT_IGOR_AUTHORIZATION_ACKNOWLEDGED_BY_OPERATOR"
        ),
        "authorization_claim_is_not_human_approval": True,
        "lineage": copy.deepcopy(dict(lineage)),
        "parent_scope_packet": {
            "path": str(parent_path),
            "sha256": parent_sha,
        },
        "scope": {
            "component_groups": EXPECTED_COMPONENT_GROUPS,
            "rows": "109/109",
            "cabinet_groups": "14/14",
            "duplicate_component_membership": 0,
            "duplicate_cabinet_membership": 0,
            "scope_expansion": False,
        },
        "ad12_mapping": {
            "mapping_request_ids": sorted(AD12_MAPPING_IDS),
            "component_code": AD12_COMPONENT_CODE,
            "install_type": AD12_INSTALL_TYPE,
            "breaking_capacity": "4,5кА",
        },
    }
    output["next_required_human_actions"] = [
        "Separate Igor authorization is required before a checked calculator run.",
        (
            "AD12 component price lookup remains fail-closed until separately "
            "authorized deterministic price mapping exists."
        ),
    ]
    return output


def apply_v02_completion(
    *,
    draft_json: Path,
    expected_draft_sha256: str,
    effective_packet_json: Path,
    expected_effective_packet_sha256: str,
    sche_product_name_decisions_json: Path,
    expected_sche_product_name_decisions_sha256: str,
    ad12_breaking_capacity_decisions_json: Path,
    expected_ad12_breaking_capacity_decisions_sha256: str,
    output_json: Path,
    application_authorized_by_igor: bool,
    applied_at_utc: str | None = None,
) -> dict[str, Any]:
    if not application_authorized_by_igor:
        raise CompletionError(
            "separate exact Igor application authorization is required"
        )
    output = output_json.expanduser().resolve(strict=False)
    if output.exists():
        raise CompletionError("output JSON already exists; overwrite is forbidden")
    if output.is_relative_to(PROJECT_ROOT):
        raise CompletionError("output JSON must be outside the Git project")
    if output.suffix.casefold() != ".json" or not output.parent.is_dir():
        raise CompletionError("output JSON parent/suffix policy failed")

    inputs = {
        "draft": draft_json.expanduser().resolve(strict=False),
        "effective_packet": effective_packet_json.expanduser().resolve(strict=False),
        "sche_product_name_decisions": (
            sche_product_name_decisions_json.expanduser().resolve(strict=False)
        ),
        "ad12_breaking_capacity_decisions": (
            ad12_breaking_capacity_decisions_json.expanduser().resolve(strict=False)
        ),
    }
    expected_hashes = {
        "draft": require_sha256(expected_draft_sha256, "expected draft SHA-256"),
        "effective_packet": require_sha256(
            expected_effective_packet_sha256,
            "expected effective packet SHA-256",
        ),
        "sche_product_name_decisions": require_sha256(
            expected_sche_product_name_decisions_sha256,
            "expected ЩЭ product-name decisions SHA-256",
        ),
        "ad12_breaking_capacity_decisions": require_sha256(
            expected_ad12_breaking_capacity_decisions_sha256,
            "expected AD12 breaking-capacity decisions SHA-256",
        ),
    }
    loaded: dict[str, dict[str, Any]] = {}
    lineage: dict[str, dict[str, str]] = {}
    before_hashes: dict[str, str] = {}
    for role, path in inputs.items():
        data, content = load_json(path, role)
        digest = sha256_bytes(content)
        if digest != expected_hashes[role]:
            raise CompletionError(f"expected SHA-256 mismatch: {role}")
        loaded[role] = data
        before_hashes[role] = digest
        lineage[role] = {"path": str(path), "sha256": digest}

    payload = complete_v02_payload(
        loaded["draft"],
        loaded["effective_packet"],
        loaded["sche_product_name_decisions"],
        loaded["ad12_breaking_capacity_decisions"],
        lineage=lineage,
        applied_at_utc=applied_at_utc or datetime.now(UTC).isoformat(),
    )
    for role, path in inputs.items():
        if sha256_bytes(path.read_bytes()) != before_hashes[role]:
            raise CompletionError(f"input changed during completion: {role}")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with output.open("x", encoding="utf-8", newline="\n") as output_file:
        output_file.write(serialized)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        apply_v02_completion(
            draft_json=args.draft_json,
            expected_draft_sha256=args.expected_draft_sha256,
            effective_packet_json=args.effective_packet_json,
            expected_effective_packet_sha256=(args.expected_effective_packet_sha256),
            sche_product_name_decisions_json=args.sche_product_name_decisions_json,
            expected_sche_product_name_decisions_sha256=(
                args.expected_sche_product_name_decisions_sha256
            ),
            ad12_breaking_capacity_decisions_json=(
                args.ad12_breaking_capacity_decisions_json
            ),
            expected_ad12_breaking_capacity_decisions_sha256=(
                args.expected_ad12_breaking_capacity_decisions_sha256
            ),
            output_json=args.output_json,
            application_authorized_by_igor=args.application_authorized_by_igor,
        )
    except CompletionError as exc:
        print(f"FAIL: {exc}")
        return 1
    print("PASS: v0.2 technical completion created; pricing not executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
