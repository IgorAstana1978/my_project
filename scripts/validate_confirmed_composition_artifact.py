"""Validate Igor-confirmed switchboard composition artifacts without pricing."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

REPORT_START = "CONFIRMED_COMPOSITION_ARTIFACT_VALIDATION_REPORT_START"
REPORT_END = "CONFIRMED_COMPOSITION_ARTIFACT_VALIDATION_REPORT_END"
MODE = "confirmed composition artifact validation only"
COMMERCIAL_STATUS = (
    "composition confirmed only; not price approval; not commercial CSV; "
    "not client-ready КП"
)
HUMAN_APPROVAL = (
    "Igor approval still required before price, commercial CSV, КП sending or "
    "production"
)
SCHEMA_VERSION = "confirmed_composition_artifact.v0.1"
APPLIED_SCHEMA_VERSION = "component_replay_applied_bundle.v0.23"
CONFIRMED_V02_SCHEMA_VERSION = "confirmed_composition_artifact.v0.2"
APPROVAL_PHRASE = "CONFIRM TECHNICAL COMPOSITION"
APPROVAL_AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
NEXT_ALLOWED_STEP = "build_price_calculator_input_draft"

ROOT_FIELDS = (
    "schema_version",
    "confirmation_id",
    "confirmed_by",
    "confirmed_at",
    "source_links",
    "safety",
    "items",
    "red_flags",
    "notes",
    "next_allowed_step",
)
SOURCE_LINK_FIELDS = (
    "raw_input_sha256",
    "preliminary_draft_sha256",
    "review_card_sha256",
)
SAFETY_FIELDS = (
    "status",
    "composition_confirmed_by_igor",
    "calculator_input_draft_allowed",
    "price_approved_by_igor",
    "commercial_csv_authorized",
    "client_style_export_authorized",
    "sending_authorized",
    "production_authorized",
)
ITEM_FIELDS = (
    "item_id",
    "product_name",
    "product_type",
    "quantity",
    "cabinet",
    "components",
    "confirmation_note",
)
CABINET_FIELDS = ("cabinet_code", "cabinet_label")
COMPONENT_FIELDS = (
    "component_id",
    "component_code",
    "component_label",
    "quantity",
    "install_type",
)
INSTALL_TYPES = {
    "modular_1p",
    "modular_2p",
    "modular_3p",
    "modular_4p",
    "diff_1p_n",
    "diff_3p_4p",
    "load_switch_1p",
    "load_switch_2p",
    "load_switch_3p",
    "load_switch_4p",
    "mccb_up_to_100a",
    "mccb_125_250a",
    "mccb_400a_plus",
    "n_pe_bus_set",
}
FORBIDDEN_KEYS = {
    "price_confirmed_by_igor",
    "price_includes_vat",
    "unit_price_kzt",
    "line_total",
    "total_kzt",
    "final_price",
    "client_ready",
    "ready_to_send",
    "send_to_client",
    "commercial_approved",
    "production_approved",
    "production_action_authorized",
    "token_execution_authorized",
    "product_name_guess",
    "product_type_guess",
    "quantity_guess",
    "cabinet_guess",
    "component_code_guess",
    "component_label_guess",
    "install_type_guess",
    "confidence",
    "evidence",
    "requires_igor_confirmation",
}
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")

APPLIED_ROOT_FIELDS = {
    "schema_version",
    "project_id",
    "application_status",
    "authority",
    "application_order",
    "source_lineage",
    "canonical_component_evidence_records",
    "prior_v0_22_application",
    "component_signature_overlays",
    "reserved_meter_space_requirements",
    "coverage",
    "confirmed_composition_created",
    "pricing_started",
    "downstream_started",
}
APPLIED_LINEAGE_FIELDS = {
    "canonical_replay_sha256",
    "canonical_replay_schema_version",
    "prior_batch_sha256",
    "prior_batch_schema_version",
    "prior_batch_id",
    "correction_batch_sha256",
    "correction_batch_schema_version",
    "correction_batch_id",
    "correction_prior_batch_id",
}
APPLIED_COVERAGE_FIELDS = {
    "canonical_component_count",
    "prior_direct_component_count",
    "prior_aggregate_member_count",
    "prior_exclusion_component_count",
    "prior_union_component_count",
    "component_signature_correction_count",
    "component_reconfirmation_count",
    "reserved_meter_space_count",
    "overlay_component_count",
}
V02_ROOT_FIELDS = {
    "schema_version",
    "project_id",
    "confirmation_id",
    "confirmed_by",
    "confirmed_at",
    "approval",
    "source_lineage",
    "installed_components",
    "reserved_meter_spaces",
    "coverage",
    "confirmed_composition_created",
    "pricing_started",
    "downstream_started",
    "red_flags",
}
V02_APPROVAL_FIELDS = {
    "authority",
    "approved_by",
    "approval_phrase",
    "approval_channel",
}
V02_SOURCE_LINEAGE_FIELDS = {
    "applied_bundle_sha256",
    "applied_bundle_schema_version",
    "applied_source_lineage",
}
V02_INSTALLED_COMPONENT_FIELDS = {
    "component_evidence_id",
    "position_id",
    "section",
    "source_locator",
    "canonical_label",
    "approved_signature",
    "quantity",
    "signature_source",
    "overlay_kind",
}
V02_QUANTITY_COMMON_FIELDS = {"decision_id", "decision_kind"}
V02_COVERAGE_FIELDS = APPLIED_COVERAGE_FIELDS | {"installed_component_count"}
APPLIED_CANONICAL_FIELDS = {
    "component_evidence_id",
    "document_id",
    "label",
    "position_id",
    "provenance",
    "section_id",
    "source_status",
}
APPLIED_PRIOR_FIELDS = {
    "application_status",
    "direct_component_quantities",
    "cabinet_level_aggregates",
    "scope_exclusions",
    "coverage",
}
APPLIED_DECISION_COMMON_FIELDS = {
    "decision_id",
    "decision_code",
    "decision_kind",
    "component_signature",
    "members",
    "application_status",
}
APPLIED_MEMBER_FIELDS = {
    "component_evidence_id",
    "evidence_position_id",
    "section",
    "source_locator",
    "canonical_label",
    "canonical_document_id",
    "canonical_source_status",
    "canonical_provenance",
}
APPLIED_SIGNATURE_FIELDS = {
    "component_identity",
    "model_type",
    "ratings",
    "poles",
    "functional_role",
}
APPLIED_OVERLAY_FIELDS = {
    "item_id",
    "item_kind",
    "cabinet_record_id",
    "cabinet_template",
    "component_evidence_id",
    "position_id",
    "section",
    "source_locator",
    "original_signature",
    "approved_signature",
    "quantity_per_cabinet",
    "provenance",
    "correction_reason",
    "canonical_evidence_modified",
    "application_status",
}
APPLIED_RESERVED_FIELDS = {
    "item_id",
    "item_kind",
    "cabinet_record_id",
    "cabinet_template",
    "component_evidence_id",
    "position_id",
    "section",
    "source_locator",
    "requirement_kind",
    "meter_connection",
    "reserved_space_per_cabinet",
    "installed_component",
    "original_identity",
    "provenance",
    "future_inclusion_requires",
    "prohibited_downstream",
    "canonical_evidence_modified",
    "application_status",
}
DIRECT_COMPONENT_QUANTITY = "DIRECT_COMPONENT_QUANTITY"
CABINET_LEVEL_AGGREGATE = "CABINET_LEVEL_AGGREGATE"
SCOPE_EXCLUSION = "SCOPE_EXCLUSION"
COMPONENT_SIGNATURE_CORRECTION = "COMPONENT_SIGNATURE_CORRECTION"
COMPONENT_RECONFIRMATION = "COMPONENT_RECONFIRMATION"
RESERVED_METER_SPACE = "RESERVED_METER_SPACE"


@dataclass
class ValidationResult:
    input_json: Path
    status: str = "FAIL"
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "JSON readable": "fail",
            "schema constants": "fail",
            "source links": "fail",
            "safety boundary": "fail",
            "items": "fail",
            "forbidden keys": "fail",
        }
    )
    red_flags: list[str] = field(default_factory=list)


class AppliedBundleValidationError(RuntimeError):
    """An applied v0.23 source cannot safely drive confirmed composition."""


@dataclass(frozen=True)
class AppliedBundleSnapshot:
    path: Path
    content: bytes
    sha256: str
    data: Mapping[str, Any]
    installed_components: list[dict[str, Any]]
    reserved_meter_spaces: list[dict[str, Any]]
    coverage: dict[str, int]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an Igor-confirmed composition artifact JSON."
    )
    parser.add_argument("--input-json", required=True, type=Path)
    parser.add_argument("--applied-bundle-json", type=Path)
    return parser.parse_args(argv)


def add_red_flag(result: ValidationResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def field_path(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def require_fields(
    data: Mapping[str, Any],
    fields: Sequence[str],
    path: str,
    result: ValidationResult,
) -> bool:
    valid = True
    for field_name in fields:
        if field_name not in data:
            valid = False
            add_red_flag(
                result,
                f"required field is missing: {field_path(path, field_name)}",
            )
    return valid


def reject_unknown_fields(
    data: Mapping[str, Any],
    allowed_fields: Sequence[str],
    path: str,
    result: ValidationResult,
) -> bool:
    valid = True
    allowed = set(allowed_fields)
    for field_name in data:
        if field_name not in allowed:
            valid = False
            add_red_flag(
                result,
                f"unknown field is not allowed: {field_path(path, field_name)}",
            )
    return valid


def require_mapping(
    value: Any,
    path: str,
    result: ValidationResult,
) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        add_red_flag(result, f"field must be an object: {path}")
        return None
    return cast(Mapping[str, Any], value)


def require_list(value: Any, path: str, result: ValidationResult) -> list[Any] | None:
    if not isinstance(value, list):
        add_red_flag(result, f"field must be a list: {path}")
        return None
    return value


def require_string(value: Any, path: str, result: ValidationResult) -> bool:
    if not is_non_empty_string(value):
        add_red_flag(result, f"field must be a non-empty string: {path}")
        return False
    return True


def require_string_list(value: Any, path: str, result: ValidationResult) -> bool:
    items = require_list(value, path, result)
    if items is None:
        return False
    valid = True
    for index, item in enumerate(items):
        if not is_non_empty_string(item):
            valid = False
            add_red_flag(
                result,
                f"list item must be a non-empty string: {path}[{index}]",
            )
    return valid


def require_positive_integer(value: Any, path: str, result: ValidationResult) -> bool:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        add_red_flag(result, f"field must be a positive integer: {path}")
        return False
    return True


def require_positive_number(value: Any, path: str, result: ValidationResult) -> bool:
    if not is_number(value) or value <= 0:
        add_red_flag(result, f"field must be a positive number: {path}")
        return False
    return True


def find_forbidden_keys(
    value: Any,
    path: str,
    result: ValidationResult,
) -> bool:
    valid = True
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = field_path(path, key_text)
            if key_text in FORBIDDEN_KEYS:
                valid = False
                add_red_flag(result, f"forbidden key present: {child_path}")
            if not find_forbidden_keys(child, child_path, result):
                valid = False
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if not find_forbidden_keys(child, f"{path}[{index}]", result):
                valid = False
    return valid


def load_json(path: Path, result: ValidationResult) -> Mapping[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        add_red_flag(result, "input JSON does not exist")
        return None
    except UnicodeDecodeError:
        add_red_flag(result, "input JSON must be valid UTF-8")
        return None
    except json.JSONDecodeError:
        add_red_flag(result, "input JSON is malformed")
        return None
    except OSError:
        add_red_flag(result, "input JSON could not be read")
        return None

    if not isinstance(raw, Mapping):
        add_red_flag(result, "JSON root must be an object")
        return None

    result.checks["JSON readable"] = "pass"
    return cast(Mapping[str, Any], raw)


def _duplicate_key_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AppliedBundleValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _applied_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AppliedBundleValidationError(f"{path} must be an object")
    return cast(Mapping[str, Any], value)


def _applied_exact(
    value: Any,
    path: str,
    fields: set[str],
) -> Mapping[str, Any]:
    mapping = _applied_mapping(value, path)
    if set(mapping) != fields:
        raise AppliedBundleValidationError(f"{path} fields mismatch")
    return mapping


def _applied_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise AppliedBundleValidationError(f"{path} must be a list")
    return value


def _applied_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AppliedBundleValidationError(f"{path} must be a non-empty string")
    return value


def _applied_positive_int(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AppliedBundleValidationError(f"{path} must be a positive integer")
    return value


def _validated_signature(value: Any, path: str) -> Mapping[str, Any]:
    return _applied_exact(value, path, APPLIED_SIGNATURE_FIELDS)


def _validated_applied_lineage(value: Any) -> Mapping[str, Any]:
    lineage = _applied_exact(
        value,
        "applied source_lineage",
        APPLIED_LINEAGE_FIELDS,
    )
    for field_name in (
        "canonical_replay_sha256",
        "prior_batch_sha256",
        "correction_batch_sha256",
    ):
        field_value = _applied_string(lineage[field_name], field_name)
        if HASH_RE.fullmatch(field_value) is None:
            raise AppliedBundleValidationError(
                f"applied source_lineage.{field_name} must be lowercase SHA-256"
            )
    expected = {
        "canonical_replay_schema_version": "component_replay_readiness_bundle.v0.2",
        "prior_batch_schema_version": "human_decisions_batch.v0.22",
        "prior_batch_id": "022",
        "correction_batch_schema_version": "human_decisions_batch.v0.23",
        "correction_batch_id": "023",
        "correction_prior_batch_id": "022",
    }
    for field_name, expected_value in expected.items():
        if lineage[field_name] != expected_value:
            raise AppliedBundleValidationError(
                f"applied source_lineage.{field_name} mismatch"
            )
    return lineage


def _quantity_projection(
    decision: Mapping[str, Any],
    kind: str,
) -> dict[str, Any]:
    quantity = {
        "decision_id": decision["decision_id"],
        "decision_kind": kind,
    }
    if kind == DIRECT_COMPONENT_QUANTITY:
        quantity["quantity_per_cabinet"] = _applied_positive_int(
            decision["quantity_per_cabinet"],
            "direct quantity_per_cabinet",
        )
    else:
        quantity["aggregate_quantity_per_cabinet"] = _applied_positive_int(
            decision["aggregate_quantity_per_cabinet"],
            "aggregate quantity_per_cabinet",
        )
        if (
            decision["applies_once_per_cabinet"] is not True
            or decision["multiply_by_member_count"] is not False
        ):
            raise AppliedBundleValidationError("aggregate quantity semantics mismatch")
        quantity["applies_once_per_cabinet"] = True
        quantity["multiply_by_member_count"] = False
    return quantity


def load_applied_bundle_snapshot(path: Path) -> AppliedBundleSnapshot:
    resolved = path.expanduser().resolve(strict=False)
    try:
        content = resolved.read_bytes()
        raw = json.loads(content, object_pairs_hook=_duplicate_key_guard)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        AppliedBundleValidationError,
    ) as exc:
        raise AppliedBundleValidationError(
            f"applied bundle cannot be read: {exc}"
        ) from exc

    applied = _applied_exact(raw, "applied bundle", APPLIED_ROOT_FIELDS)
    expected_root = {
        "schema_version": APPLIED_SCHEMA_VERSION,
        "application_status": "APPLIED",
        "authority": APPROVAL_AUTHORITY,
        "application_order": [
            "human_decisions_batch.v0.22",
            "human_decisions_batch.v0.23",
        ],
        "confirmed_composition_created": False,
        "pricing_started": False,
        "downstream_started": False,
    }
    for field_name, expected_value in expected_root.items():
        if applied[field_name] != expected_value:
            raise AppliedBundleValidationError(f"applied bundle {field_name} mismatch")
    _applied_string(applied["project_id"], "applied project_id")
    _validated_applied_lineage(applied["source_lineage"])

    canonical_by_id: dict[str, Mapping[str, Any]] = {}
    for raw_record in _applied_list(
        applied["canonical_component_evidence_records"],
        "canonical_component_evidence_records",
    ):
        record = _applied_exact(
            raw_record,
            "canonical component record",
            APPLIED_CANONICAL_FIELDS,
        )
        component_id = _applied_string(
            record["component_evidence_id"],
            "canonical component_evidence_id",
        )
        _applied_string(record["label"], "canonical label")
        if component_id in canonical_by_id:
            raise AppliedBundleValidationError("duplicate canonical COMP")
        canonical_by_id[component_id] = record
    if not canonical_by_id:
        raise AppliedBundleValidationError("canonical records must be non-empty")

    prior = _applied_exact(
        applied["prior_v0_22_application"],
        "prior_v0_22_application",
        APPLIED_PRIOR_FIELDS,
    )
    if prior["application_status"] != "APPLIED":
        raise AppliedBundleValidationError("prior_v0_22_application status mismatch")

    installed_members: list[tuple[Mapping[str, Any], Mapping[str, Any], str]] = []
    excluded_ids: set[str] = set()
    prior_ids: set[str] = set()
    counts = {
        "prior_direct_component_count": 0,
        "prior_aggregate_member_count": 0,
        "prior_exclusion_component_count": 0,
    }
    decision_specs = (
        (
            "direct_component_quantities",
            DIRECT_COMPONENT_QUANTITY,
            APPLIED_DECISION_COMMON_FIELDS | {"quantity_per_cabinet"},
            "prior_direct_component_count",
        ),
        (
            "cabinet_level_aggregates",
            CABINET_LEVEL_AGGREGATE,
            APPLIED_DECISION_COMMON_FIELDS
            | {
                "aggregate_quantity_per_cabinet",
                "applies_once_per_cabinet",
                "multiply_by_member_count",
            },
            "prior_aggregate_member_count",
        ),
        (
            "scope_exclusions",
            SCOPE_EXCLUSION,
            APPLIED_DECISION_COMMON_FIELDS
            | {
                "scope_status",
                "future_inclusion_requires",
                "prohibited_downstream",
            },
            "prior_exclusion_component_count",
        ),
    )
    decision_ids: set[str] = set()
    for list_name, kind, fields, count_name in decision_specs:
        for raw_decision in _applied_list(prior[list_name], list_name):
            decision = _applied_exact(raw_decision, list_name, fields)
            decision_id = _applied_string(
                decision["decision_id"],
                f"{list_name} decision_id",
            )
            if decision_id in decision_ids:
                raise AppliedBundleValidationError("duplicate prior decision_id")
            decision_ids.add(decision_id)
            if (
                decision["decision_kind"] != kind
                or decision["application_status"] != "APPLIED"
            ):
                raise AppliedBundleValidationError(
                    f"{list_name} decision contract mismatch"
                )
            signature = _validated_signature(
                decision["component_signature"],
                f"{list_name} component_signature",
            )
            if kind != SCOPE_EXCLUSION:
                _quantity_projection(decision, kind)
            members = _applied_list(decision["members"], f"{list_name} members")
            if not members:
                raise AppliedBundleValidationError(
                    f"{list_name} members must be non-empty"
                )
            for raw_member in members:
                member = _applied_exact(
                    raw_member,
                    f"{list_name} member",
                    APPLIED_MEMBER_FIELDS,
                )
                component_id = _applied_string(
                    member["component_evidence_id"],
                    f"{list_name} component_evidence_id",
                )
                if component_id in prior_ids:
                    raise AppliedBundleValidationError("duplicate prior COMP")
                if component_id not in canonical_by_id:
                    raise AppliedBundleValidationError("unknown prior COMP")
                canonical = canonical_by_id[component_id]
                if (
                    member["canonical_label"] != canonical["label"]
                    or member["evidence_position_id"] != canonical["position_id"]
                    or member["section"] != canonical["section_id"]
                ):
                    raise AppliedBundleValidationError(
                        f"{component_id} prior canonical binding mismatch"
                    )
                prior_ids.add(component_id)
                counts[count_name] += 1
                if kind == SCOPE_EXCLUSION:
                    excluded_ids.add(component_id)
                else:
                    installed_members.append((decision, member, kind))
                    _validated_signature(
                        signature,
                        f"{component_id} component_signature",
                    )

    overlays_by_id: dict[str, Mapping[str, Any]] = {}
    correction_count = 0
    reconfirmation_count = 0
    for raw_overlay in _applied_list(
        applied["component_signature_overlays"],
        "component_signature_overlays",
    ):
        overlay = _applied_exact(
            raw_overlay,
            "component signature overlay",
            APPLIED_OVERLAY_FIELDS,
        )
        component_id = _applied_string(
            overlay["component_evidence_id"],
            "overlay component_evidence_id",
        )
        if component_id in overlays_by_id:
            raise AppliedBundleValidationError("duplicate overlay COMP")
        if component_id not in canonical_by_id or component_id not in prior_ids:
            raise AppliedBundleValidationError("unknown overlay COMP")
        if component_id in excluded_ids:
            raise AppliedBundleValidationError(
                "installed overlay references excluded COMP"
            )
        kind = overlay["item_kind"]
        if kind == COMPONENT_SIGNATURE_CORRECTION:
            correction_count += 1
        elif kind == COMPONENT_RECONFIRMATION:
            reconfirmation_count += 1
        else:
            raise AppliedBundleValidationError("unknown overlay kind")
        approved_signature = _validated_signature(
            overlay["approved_signature"],
            "overlay approved_signature",
        )
        if (
            approved_signature["component_identity"]
            != canonical_by_id[component_id]["label"]
        ):
            raise AppliedBundleValidationError(
                f"{component_id} overlay canonical identity mismatch"
            )
        if (
            overlay["canonical_evidence_modified"] is not False
            or overlay["application_status"] != "APPLIED"
        ):
            raise AppliedBundleValidationError("overlay boundary mismatch")
        overlays_by_id[component_id] = overlay

    reserved: list[dict[str, Any]] = []
    reserved_ids: set[str] = set()
    for raw_requirement in _applied_list(
        applied["reserved_meter_space_requirements"],
        "reserved_meter_space_requirements",
    ):
        requirement = _applied_exact(
            raw_requirement,
            "reserved meter space requirement",
            APPLIED_RESERVED_FIELDS,
        )
        component_id = _applied_string(
            requirement["component_evidence_id"],
            "reserved component_evidence_id",
        )
        if component_id in reserved_ids or component_id in overlays_by_id:
            raise AppliedBundleValidationError("duplicate overlay or reserved COMP")
        if component_id not in canonical_by_id or component_id not in excluded_ids:
            raise AppliedBundleValidationError("unknown reserved COMP")
        if (
            requirement["item_kind"] != RESERVED_METER_SPACE
            or requirement["requirement_kind"] != RESERVED_METER_SPACE
            or requirement["installed_component"] is not False
            or requirement["reserved_space_per_cabinet"] != 1
            or requirement["canonical_evidence_modified"] is not False
            or requirement["application_status"] != "APPLIED"
        ):
            raise AppliedBundleValidationError("reserved meter space boundary mismatch")
        reserved_ids.add(component_id)
        reserved.append(copy.deepcopy(dict(requirement)))

    installed_components: list[dict[str, Any]] = []
    installed_ids: set[str] = set()
    for decision, member, kind in installed_members:
        component_id = cast(str, member["component_evidence_id"])
        if component_id in installed_ids or component_id in reserved_ids:
            raise AppliedBundleValidationError("duplicate installed or reserved COMP")
        overlay = overlays_by_id.get(component_id)
        installed_components.append(
            {
                "component_evidence_id": component_id,
                "position_id": member["evidence_position_id"],
                "section": member["section"],
                "source_locator": member["source_locator"],
                "canonical_label": member["canonical_label"],
                "approved_signature": copy.deepcopy(
                    overlay["approved_signature"]
                    if overlay is not None
                    else decision["component_signature"]
                ),
                "quantity": _quantity_projection(decision, kind),
                "signature_source": (
                    "V0_23_OVERLAY" if overlay is not None else "V0_22_PRIOR"
                ),
                "overlay_kind": (overlay["item_kind"] if overlay is not None else None),
            }
        )
        installed_ids.add(component_id)

    if set(overlays_by_id) - installed_ids:
        raise AppliedBundleValidationError(
            "overlay COMP is absent from installed composition"
        )

    derived_coverage = {
        "canonical_component_count": len(canonical_by_id),
        **counts,
        "prior_union_component_count": len(prior_ids),
        "component_signature_correction_count": correction_count,
        "component_reconfirmation_count": reconfirmation_count,
        "reserved_meter_space_count": len(reserved_ids),
        "overlay_component_count": len(overlays_by_id) + len(reserved_ids),
    }
    applied_coverage = _applied_exact(
        applied["coverage"],
        "applied coverage",
        APPLIED_COVERAGE_FIELDS,
    )
    if dict(applied_coverage) != derived_coverage:
        raise AppliedBundleValidationError("applied coverage mismatch")
    prior_coverage = _applied_mapping(prior["coverage"], "prior coverage")
    for field_name in (
        "direct_component_count",
        "aggregate_member_count",
        "exclusion_component_count",
        "union_component_count",
    ):
        expected_name = {
            "direct_component_count": "prior_direct_component_count",
            "aggregate_member_count": "prior_aggregate_member_count",
            "exclusion_component_count": "prior_exclusion_component_count",
            "union_component_count": "prior_union_component_count",
        }[field_name]
        if prior_coverage.get(field_name) != derived_coverage[expected_name]:
            raise AppliedBundleValidationError(f"prior coverage {field_name} mismatch")

    confirmed_coverage = {
        **derived_coverage,
        "installed_component_count": len(installed_components),
    }
    return AppliedBundleSnapshot(
        path=resolved,
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        data=applied,
        installed_components=installed_components,
        reserved_meter_spaces=reserved,
        coverage=confirmed_coverage,
    )


def validate_schema_constants(
    data: Mapping[str, Any],
    result: ValidationResult,
) -> None:
    valid = True
    if not require_fields(data, ROOT_FIELDS, "", result):
        valid = False
    if not reject_unknown_fields(data, ROOT_FIELDS, "", result):
        valid = False
    if data.get("schema_version") != SCHEMA_VERSION:
        valid = False
        add_red_flag(
            result,
            "schema_version must be confirmed_composition_artifact.v0.1",
        )
    for field_name in ("confirmation_id", "confirmed_by", "confirmed_at"):
        if field_name in data and not require_string(
            data[field_name],
            field_name,
            result,
        ):
            valid = False
    if data.get("next_allowed_step") != NEXT_ALLOWED_STEP:
        valid = False
        add_red_flag(
            result,
            "next_allowed_step must be build_price_calculator_input_draft",
        )
    if "red_flags" in data and not require_string_list(
        data["red_flags"],
        "red_flags",
        result,
    ):
        valid = False
    if "notes" in data and not require_string_list(data["notes"], "notes", result):
        valid = False
    result.checks["schema constants"] = "pass" if valid else "fail"


def validate_source_links(data: Any, result: ValidationResult) -> None:
    source_links = require_mapping(data, "source_links", result)
    if source_links is None:
        return

    valid = True
    if not require_fields(source_links, SOURCE_LINK_FIELDS, "source_links", result):
        valid = False
    if not reject_unknown_fields(
        source_links,
        SOURCE_LINK_FIELDS,
        "source_links",
        result,
    ):
        valid = False

    for field_name in SOURCE_LINK_FIELDS:
        value = source_links.get(field_name)
        if not isinstance(value, str) or HASH_RE.fullmatch(value) is None:
            valid = False
            add_red_flag(
                result,
                f"source_links.{field_name} must be 64 lowercase hex characters",
            )

    result.checks["source links"] = "pass" if valid else "fail"


def validate_safety(data: Any, result: ValidationResult) -> None:
    safety = require_mapping(data, "safety", result)
    if safety is None:
        return

    valid = True
    if not require_fields(safety, SAFETY_FIELDS, "safety", result):
        valid = False
    if not reject_unknown_fields(safety, SAFETY_FIELDS, "safety", result):
        valid = False
    if safety.get("status") != "confirmed_composition_only":
        valid = False
        add_red_flag(result, "safety.status must be confirmed_composition_only")
    if safety.get("composition_confirmed_by_igor") is not True:
        valid = False
        add_red_flag(result, "safety.composition_confirmed_by_igor must be true")
    if safety.get("calculator_input_draft_allowed") is not True:
        valid = False
        add_red_flag(result, "safety.calculator_input_draft_allowed must be true")

    required_false = (
        "price_approved_by_igor",
        "commercial_csv_authorized",
        "client_style_export_authorized",
        "sending_authorized",
        "production_authorized",
    )
    for field_name in required_false:
        value = safety.get(field_name)
        if value is not False:
            valid = False
            add_red_flag(result, f"safety.{field_name} must be false")
        if value is True:
            add_red_flag(result, f"safety authorization is true: safety.{field_name}")

    result.checks["safety boundary"] = "pass" if valid else "fail"


def validate_cabinet(data: Any, path: str, result: ValidationResult) -> bool:
    cabinet = require_mapping(data, path, result)
    if cabinet is None:
        return False

    valid = True
    if not require_fields(cabinet, CABINET_FIELDS, path, result):
        valid = False
    if not reject_unknown_fields(cabinet, CABINET_FIELDS, path, result):
        valid = False
    for field_name in CABINET_FIELDS:
        if field_name in cabinet and not require_string(
            cabinet[field_name],
            field_path(path, field_name),
            result,
        ):
            valid = False
    return valid


def validate_component(data: Any, path: str, result: ValidationResult) -> bool:
    component = require_mapping(data, path, result)
    if component is None:
        return False

    valid = True
    if not require_fields(component, COMPONENT_FIELDS, path, result):
        valid = False
    if not reject_unknown_fields(component, COMPONENT_FIELDS, path, result):
        valid = False
    for field_name in ("component_id", "component_code", "component_label"):
        if field_name in component and not require_string(
            component[field_name],
            field_path(path, field_name),
            result,
        ):
            valid = False
    if "quantity" in component and not require_positive_number(
        component["quantity"],
        field_path(path, "quantity"),
        result,
    ):
        valid = False

    install_type = component.get("install_type")
    if install_type == "manual_review_required":
        valid = False
        add_red_flag(result, f"manual_review_required is not allowed: {path}")
    elif install_type not in INSTALL_TYPES:
        valid = False
        add_red_flag(result, f"install_type is not allowed: {path}")
    return valid


def validate_item(data: Any, path: str, result: ValidationResult) -> bool:
    item = require_mapping(data, path, result)
    if item is None:
        return False

    valid = True
    if not require_fields(item, ITEM_FIELDS, path, result):
        valid = False
    if not reject_unknown_fields(item, ITEM_FIELDS, path, result):
        valid = False
    for field_name in (
        "item_id",
        "product_name",
        "product_type",
        "confirmation_note",
    ):
        if field_name in item and not require_string(
            item[field_name],
            field_path(path, field_name),
            result,
        ):
            valid = False
    if "quantity" in item and not require_positive_integer(
        item["quantity"],
        field_path(path, "quantity"),
        result,
    ):
        valid = False
    if "cabinet" in item and not validate_cabinet(
        item["cabinet"],
        field_path(path, "cabinet"),
        result,
    ):
        valid = False

    components = item.get("components")
    component_list = require_list(components, field_path(path, "components"), result)
    if component_list is None:
        valid = False
    elif not component_list:
        valid = False
        add_red_flag(result, f"field must be a non-empty list: {path}.components")
    else:
        for index, component in enumerate(component_list):
            if not validate_component(component, f"{path}.components[{index}]", result):
                valid = False

    return valid


def validate_items(data: Any, result: ValidationResult) -> None:
    item_list = require_list(data, "items", result)
    if item_list is None:
        return
    if not item_list:
        add_red_flag(result, "items must be a non-empty list")
        return

    valid = True
    for index, item in enumerate(item_list):
        if not validate_item(item, f"items[{index}]", result):
            valid = False

    result.checks["items"] = "pass" if valid else "fail"


def validate_v02_artifact(
    data: Mapping[str, Any],
    result: ValidationResult,
    applied_bundle_json: Path | None,
) -> None:
    result.checks = {
        "JSON readable": "pass",
        "schema constants": "fail",
        "exact Igor approval": "fail",
        "applied SHA and lineage": "fail",
        "installed composition": "fail",
        "reserved meter spaces": "fail",
        "coverage": "fail",
        "downstream boundary": "fail",
    }
    if set(data) != V02_ROOT_FIELDS:
        add_red_flag(result, "confirmed v0.2 root fields mismatch")
        return
    schema_valid = True
    for field_name in (
        "project_id",
        "confirmation_id",
        "confirmed_by",
        "confirmed_at",
    ):
        if not require_string(data[field_name], field_name, result):
            schema_valid = False
    if (
        data["schema_version"] != CONFIRMED_V02_SCHEMA_VERSION
        or data["confirmed_by"] != "Igor"
        or data["red_flags"] != []
    ):
        schema_valid = False
        add_red_flag(result, "confirmed v0.2 schema constants mismatch")
    result.checks["schema constants"] = "pass" if schema_valid else "fail"

    approval = require_mapping(data["approval"], "approval", result)
    if approval is not None:
        approval_valid = set(approval) == V02_APPROVAL_FIELDS
        expected_approval = {
            "authority": APPROVAL_AUTHORITY,
            "approved_by": "Igor",
            "approval_phrase": APPROVAL_PHRASE,
        }
        for field_name, expected_value in expected_approval.items():
            if approval.get(field_name) != expected_value:
                approval_valid = False
                add_red_flag(
                    result,
                    f"approval.{field_name} exact Igor approval mismatch",
                )
        if not require_string(
            approval.get("approval_channel"),
            "approval.approval_channel",
            result,
        ):
            approval_valid = False
        result.checks["exact Igor approval"] = "pass" if approval_valid else "fail"

    boundary_valid = True
    expected_boundary = {
        "confirmed_composition_created": True,
        "pricing_started": False,
        "downstream_started": False,
    }
    for field_name, expected_value in expected_boundary.items():
        if data[field_name] is not expected_value:
            boundary_valid = False
            add_red_flag(
                result,
                f"{field_name} must be {str(expected_value).lower()}",
            )
    result.checks["downstream boundary"] = "pass" if boundary_valid else "fail"

    if applied_bundle_json is None:
        add_red_flag(
            result,
            "applied bundle JSON is required for confirmed v0.2 validation",
        )
        return
    try:
        snapshot = load_applied_bundle_snapshot(applied_bundle_json)
    except AppliedBundleValidationError as exc:
        add_red_flag(result, str(exc))
        return

    source_valid = True
    source_lineage = require_mapping(
        data["source_lineage"],
        "source_lineage",
        result,
    )
    if source_lineage is None:
        source_valid = False
    else:
        if set(source_lineage) != V02_SOURCE_LINEAGE_FIELDS:
            source_valid = False
            add_red_flag(result, "confirmed v0.2 source_lineage fields mismatch")
        if source_lineage.get("applied_bundle_sha256") != snapshot.sha256:
            source_valid = False
            add_red_flag(result, "applied bundle SHA-256 binding mismatch")
        if (
            source_lineage.get("applied_bundle_schema_version")
            != APPLIED_SCHEMA_VERSION
        ):
            source_valid = False
            add_red_flag(result, "applied bundle schema lineage mismatch")
        if source_lineage.get("applied_source_lineage") != snapshot.data.get(
            "source_lineage"
        ):
            source_valid = False
            add_red_flag(result, "applied source lineage mismatch")
    if data["project_id"] != snapshot.data["project_id"]:
        source_valid = False
        add_red_flag(result, "confirmed project_id differs from applied bundle")
    result.checks["applied SHA and lineage"] = "pass" if source_valid else "fail"

    installed = require_list(
        data["installed_components"],
        "installed_components",
        result,
    )
    installed_valid = installed == snapshot.installed_components
    installed_ids: list[Any] = []
    if installed is not None:
        for index, raw_component in enumerate(installed):
            component = require_mapping(
                raw_component,
                f"installed_components[{index}]",
                result,
            )
            if component is None:
                installed_valid = False
                continue
            if set(component) != V02_INSTALLED_COMPONENT_FIELDS:
                installed_valid = False
                add_red_flag(
                    result,
                    f"installed_components[{index}] fields mismatch",
                )
            component_id = component.get("component_evidence_id")
            if not isinstance(component_id, str):
                installed_valid = False
                add_red_flag(
                    result,
                    f"installed_components[{index}] COMP must be a string",
                )
            else:
                installed_ids.append(component_id)
    if len(installed_ids) != len(set(installed_ids)):
        installed_valid = False
        add_red_flag(result, "duplicate installed COMP")
    if installed != snapshot.installed_components:
        add_red_flag(
            result,
            "installed composition differs from applied v0.23 projection",
        )
    result.checks["installed composition"] = "pass" if installed_valid else "fail"

    reserved = require_list(
        data["reserved_meter_spaces"],
        "reserved_meter_spaces",
        result,
    )
    reserved_valid = reserved == snapshot.reserved_meter_spaces
    reserved_ids: list[Any] = []
    if reserved is not None:
        for index, raw_requirement in enumerate(reserved):
            requirement = require_mapping(
                raw_requirement,
                f"reserved_meter_spaces[{index}]",
                result,
            )
            if requirement is None:
                reserved_valid = False
                continue
            component_id = requirement.get("component_evidence_id")
            if not isinstance(component_id, str):
                reserved_valid = False
                add_red_flag(
                    result,
                    f"reserved_meter_spaces[{index}] COMP must be a string",
                )
            else:
                reserved_ids.append(component_id)
            if requirement.get("installed_component") is not False:
                reserved_valid = False
                add_red_flag(
                    result,
                    "reserved meter space installed_component must be false",
                )
    if len(reserved_ids) != len(set(reserved_ids)):
        reserved_valid = False
        add_red_flag(result, "duplicate reserved COMP")
    if set(installed_ids) & set(reserved_ids):
        reserved_valid = False
        add_red_flag(result, "reserved space leaked into installed composition")
    if reserved != snapshot.reserved_meter_spaces:
        add_red_flag(
            result,
            "reserved meter spaces differ from applied v0.23 projection",
        )
    result.checks["reserved meter spaces"] = "pass" if reserved_valid else "fail"

    coverage_valid = data["coverage"] == snapshot.coverage
    if not coverage_valid:
        add_red_flag(result, "confirmed v0.2 coverage mismatch")
    result.checks["coverage"] = "pass" if coverage_valid else "fail"


def validate_confirmed_composition_artifact(
    input_json: Path,
    applied_bundle_json: Path | None = None,
) -> ValidationResult:
    result = ValidationResult(input_json=input_json.expanduser().resolve(strict=False))
    data = load_json(result.input_json, result)
    if data is None:
        return result

    schema_version = data.get("schema_version")
    if schema_version == CONFIRMED_V02_SCHEMA_VERSION:
        validate_v02_artifact(data, result, applied_bundle_json)
        all_checks_pass = all(status == "pass" for status in result.checks.values())
        result.status = "PASS" if all_checks_pass and not result.red_flags else "FAIL"
        return result
    if schema_version != SCHEMA_VERSION:
        add_red_flag(
            result,
            "schema_version must be confirmed_composition_artifact.v0.1 or v0.2",
        )
        return result
    if applied_bundle_json is not None:
        add_red_flag(
            result,
            "applied bundle input is forbidden for confirmed v0.1",
        )

    forbidden_ok = find_forbidden_keys(data, "", result)
    result.checks["forbidden keys"] = "pass" if forbidden_ok else "fail"
    validate_schema_constants(data, result)
    validate_source_links(data.get("source_links"), result)
    validate_safety(data.get("safety"), result)
    validate_items(data.get("items"), result)

    all_checks_pass = all(status == "pass" for status in result.checks.values())
    result.status = "PASS" if all_checks_pass and not result.red_flags else "FAIL"
    return result


def format_items(values: Sequence[str]) -> list[str]:
    return list(values) if values else ["none"]


def format_report(result: ValidationResult) -> str:
    lines = [
        REPORT_START,
        "",
        "Status:",
        result.status,
        "",
        "Mode:",
        MODE,
        "",
        "Checks:",
    ]
    lines.extend(f"{name}: {status}" for name, status in result.checks.items())
    lines.extend(["", "Red flags:"])
    lines.extend(format_items(result.red_flags))
    lines.extend(
        [
            "",
            "Commercial status:",
            COMMERCIAL_STATUS,
            "",
            "Human Approval:",
            HUMAN_APPROVAL,
            "",
            REPORT_END,
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_confirmed_composition_artifact(
        args.input_json,
        applied_bundle_json=args.applied_bundle_json,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
