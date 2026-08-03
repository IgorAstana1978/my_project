"""Build an unfilled pricing-input draft from confirmed composition v0.2."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = Path(__file__).with_name("validate_confirmed_composition_artifact.py")

SCHEMA_VERSION = "price_calculator_input_draft.v0.2"
DRAFT_TYPE = "price_calculator_input_draft"
CONFIRMED_SCHEMA_VERSION = "confirmed_composition_artifact.v0.2"
APPLIED_SCHEMA_VERSION = "component_replay_applied_bundle.v0.23"
MAPPING_STATUS = "IGOR_REQUIRED"
CSV_KIND = "confirmed_composition_csv_row_drafts"
CSV_DELIMITER = ";"
CALCULATOR_COLUMNS = (
    "product_name",
    "cabinet_code",
    "consumables_factor",
    "component_code",
    "component_qty",
    "install_type",
)
DIRECT_COMPONENT_QUANTITY = "DIRECT_COMPONENT_QUANTITY"
CABINET_LEVEL_AGGREGATE = "CABINET_LEVEL_AGGREGATE"
CORRECTION = "COMPONENT_SIGNATURE_CORRECTION"
RECONFIRMATION = "COMPONENT_RECONFIRMATION"

REPORT_START = "PRICE_CALCULATOR_INPUT_DRAFT_V02_BRIDGE_REPORT_START"
REPORT_END = "PRICE_CALCULATOR_INPUT_DRAFT_V02_BRIDGE_REPORT_END"
MODE = "unfilled pricing-input draft build only; no price calculation"
NEXT_REQUIRED_HUMAN_ACTIONS = (
    "Igor maps each cabinet group to product_name, cabinet_code, and "
    "consumables_factor.",
    "Igor maps each row draft to component_code and install_type.",
    "Igor separately authorizes any future calculator run using a completed "
    "and validated draft.",
)

ROOT_FIELDS = {
    "schema_version",
    "draft_type",
    "source",
    "cabinet_groups",
    "calculator_input_format",
    "coverage",
    "safety",
    "next_required_human_actions",
}
SOURCE_FIELDS = {
    "project_id",
    "confirmation_id",
    "confirmed_composition_schema_version",
    "confirmed_composition_sha256",
    "applied_bundle_schema_version",
    "applied_bundle_sha256",
    "applied_source_lineage",
}
CABINET_GROUP_FIELDS = {
    "cabinet_group_id",
    "source_cabinet_template",
    "product_name",
    "cabinet_code",
    "cabinet_label",
    "consumables_factor",
    "mapping_status",
    "row_draft_ids",
}
FORMAT_FIELDS = {"kind", "delimiter", "columns", "row_drafts"}
ROW_FIELDS = {
    "row_id",
    "cabinet_group_id",
    "calculator_values",
    "source_quantity",
    "source_component_evidence_ids",
    "approved_signature",
    "mapping_status",
}
CALCULATOR_VALUE_FIELDS = set(CALCULATOR_COLUMNS)
COVERAGE_FIELDS = {
    "installed_component_count",
    "direct_installed_component_count",
    "aggregate_member_count",
    "aggregate_decision_count",
    "pricing_row_draft_count",
    "cabinet_group_count",
    "reserved_meter_space_count",
    "reserved_excluded_from_pricing_count",
    "correction_count",
    "reconfirmation_count",
}
SAFETY_FIELDS = {
    "price_calculation_executed",
    "pricing_started",
    "price_approved_by_igor",
    "commercial_csv_authorized",
    "sending_authorized",
    "production_authorized",
    "downstream_started",
}


class BridgeError(RuntimeError):
    """The v0.2 pricing-input bridge cannot proceed safely."""


@dataclass(frozen=True)
class PriorBinding:
    decision: Mapping[str, Any]
    member: Mapping[str, Any]
    decision_kind: str
    cabinet_template: str


@dataclass
class BuildResult:
    confirmed_composition_json: Path
    applied_bundle_json: Path
    output_json: Path
    status: str = "FAIL"
    output_created: bool = False
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "output policy": "fail",
            "confirmed and applied validation": "fail",
            "quantity and cabinet projection": "fail",
            "in-memory output validation": "fail",
            "input drift": "fail",
            "atomic no-overwrite publication": "fail",
            "safety boundary": "fail",
        }
    )
    red_flags: list[str] = field(default_factory=list)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build an unfilled price_calculator_input_draft.v0.2 from exact "
            "confirmed composition v0.2 and applied bundle v0.23 inputs."
        )
    )
    parser.add_argument("--confirmed-composition-json", required=True, type=Path)
    parser.add_argument("--applied-bundle-json", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def add_red_flag(result: BuildResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def validate_output_policy(result: BuildResult) -> None:
    output = result.output_json
    if output.exists():
        raise BridgeError("output JSON already exists; overwrite is forbidden")
    if is_inside_project(output):
        raise BridgeError("output JSON must be outside the Git project")
    if not output.parent.is_dir():
        raise BridgeError("output parent directory does not exist")
    result.checks["output policy"] = "pass"


def load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_confirmed_composition_artifact_for_v02_pricing_bridge",
        VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise BridgeError("confirmed composition validator could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def duplicate_key_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise BridgeError(f"duplicate JSON key is forbidden: {key}")
        value[key] = child
    return value


def load_exact_json(path: Path, description: str) -> tuple[Mapping[str, Any], bytes]:
    try:
        content = path.read_bytes()
        value = json.loads(content, object_pairs_hook=duplicate_key_guard)
    except BridgeError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError(f"{description} cannot be read: {exc}") from exc
    if not isinstance(value, Mapping):
        raise BridgeError(f"{description} root must be an object")
    return cast(Mapping[str, Any], value), content


def validate_sources(
    result: BuildResult,
) -> tuple[Mapping[str, Any], Any, str]:
    validator = load_validator_module()
    validation = validator.validate_confirmed_composition_artifact(
        result.confirmed_composition_json,
        applied_bundle_json=result.applied_bundle_json,
    )
    if validation.status != "PASS":
        detail = "; ".join(validation.red_flags) or "unknown validation failure"
        raise BridgeError(f"confirmed/applied validation failed: {detail}")

    confirmed, confirmed_content = load_exact_json(
        result.confirmed_composition_json,
        "confirmed composition JSON",
    )
    try:
        snapshot = validator.load_applied_bundle_snapshot(result.applied_bundle_json)
    except validator.AppliedBundleValidationError as exc:
        raise BridgeError(f"applied bundle validation failed: {exc}") from exc

    if confirmed.get("schema_version") != CONFIRMED_SCHEMA_VERSION:
        raise BridgeError("only confirmed_composition_artifact.v0.2 is accepted")
    if snapshot.data.get("schema_version") != APPLIED_SCHEMA_VERSION:
        raise BridgeError("only component_replay_applied_bundle.v0.23 is accepted")
    source_lineage = confirmed.get("source_lineage")
    if not isinstance(source_lineage, Mapping):
        raise BridgeError("confirmed source_lineage must be an object")
    if (
        source_lineage.get("applied_bundle_sha256") != snapshot.sha256
        or source_lineage.get("applied_bundle_schema_version") != APPLIED_SCHEMA_VERSION
        or source_lineage.get("applied_source_lineage")
        != snapshot.data.get("source_lineage")
    ):
        raise BridgeError("confirmed/applied SHA or lineage binding mismatch")

    result.checks["confirmed and applied validation"] = "pass"
    return (
        confirmed,
        snapshot,
        hashlib.sha256(confirmed_content).hexdigest(),
    )


def require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BridgeError(f"{path} must be an object")
    return cast(Mapping[str, Any], value)


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise BridgeError(f"{path} must be a list")
    return value


def require_non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BridgeError(f"{path} must be a non-empty string")
    return value


def require_positive_int(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise BridgeError(f"{path} must be a positive integer")
    return value


def build_prior_bindings(applied: Mapping[str, Any]) -> dict[str, PriorBinding]:
    prior = require_mapping(
        applied.get("prior_v0_22_application"),
        "prior_v0_22_application",
    )
    bindings: dict[str, PriorBinding] = {}
    specifications = (
        ("direct_component_quantities", DIRECT_COMPONENT_QUANTITY),
        ("cabinet_level_aggregates", CABINET_LEVEL_AGGREGATE),
    )
    for list_name, expected_kind in specifications:
        for raw_decision in require_list(prior.get(list_name), list_name):
            decision = require_mapping(raw_decision, f"{list_name} decision")
            if decision.get("decision_kind") != expected_kind:
                raise BridgeError(f"{list_name} decision kind mismatch")
            signature = require_mapping(
                decision.get("component_signature"),
                f"{list_name} component_signature",
            )
            cabinet_template = require_non_empty_string(
                signature.get("cabinet_template"),
                f"{list_name} component_signature.cabinet_template",
            )
            for raw_member in require_list(
                decision.get("members"),
                f"{list_name} members",
            ):
                member = require_mapping(raw_member, f"{list_name} member")
                component_id = require_non_empty_string(
                    member.get("component_evidence_id"),
                    f"{list_name} member.component_evidence_id",
                )
                if component_id in bindings:
                    raise BridgeError(
                        f"ambiguous v0.22 prior binding for {component_id}"
                    )
                bindings[component_id] = PriorBinding(
                    decision=decision,
                    member=member,
                    decision_kind=expected_kind,
                    cabinet_template=cabinet_template,
                )
    return bindings


def cabinet_group_ids(
    installed: list[Any],
    bindings: Mapping[str, PriorBinding],
) -> tuple[dict[str, str], list[str]]:
    template_to_group: dict[str, str] = {}
    ordered_templates: list[str] = []
    for raw_component in installed:
        component = require_mapping(raw_component, "installed component")
        component_id = require_non_empty_string(
            component.get("component_evidence_id"),
            "installed component.component_evidence_id",
        )
        binding = bindings.get(component_id)
        if binding is None:
            raise BridgeError(f"missing v0.22 prior binding for {component_id}")
        template = binding.cabinet_template
        if template not in template_to_group:
            ordered_templates.append(template)
            template_to_group[template] = f"CABINET-GROUP-{len(ordered_templates):03d}"
    return template_to_group, ordered_templates


def calculator_values(component_qty: int) -> dict[str, Any]:
    return {
        "product_name": None,
        "cabinet_code": None,
        "consumables_factor": None,
        "component_code": None,
        "component_qty": component_qty,
        "install_type": None,
    }


def verify_direct_quantity(
    component_id: str,
    quantity: Mapping[str, Any],
    binding: PriorBinding,
) -> int:
    decision = binding.decision
    if (
        binding.decision_kind != DIRECT_COMPONENT_QUANTITY
        or quantity.get("decision_kind") != DIRECT_COMPONENT_QUANTITY
        or quantity.get("decision_id") != decision.get("decision_id")
    ):
        raise BridgeError(f"direct quantity binding mismatch for {component_id}")
    value = require_positive_int(
        quantity.get("quantity_per_cabinet"),
        f"{component_id} quantity_per_cabinet",
    )
    if value != decision.get("quantity_per_cabinet"):
        raise BridgeError(f"direct quantity value mismatch for {component_id}")
    return value


def aggregate_row(
    decision_id: str,
    components: list[Mapping[str, Any]],
    bindings: Mapping[str, PriorBinding],
    template_to_group: Mapping[str, str],
    row_id: str,
) -> dict[str, Any]:
    if not components:
        raise BridgeError(f"aggregate {decision_id} has no installed members")
    first = components[0]
    first_id = require_non_empty_string(
        first.get("component_evidence_id"),
        "aggregate component_evidence_id",
    )
    first_binding = bindings.get(first_id)
    if first_binding is None:
        raise BridgeError(f"missing v0.22 prior binding for {first_id}")
    decision = first_binding.decision
    if (
        first_binding.decision_kind != CABINET_LEVEL_AGGREGATE
        or decision.get("decision_id") != decision_id
    ):
        raise BridgeError(f"aggregate prior binding mismatch for {decision_id}")

    source_quantity = copy.deepcopy(
        dict(require_mapping(first.get("quantity"), f"{first_id} quantity"))
    )
    expected_quantity = {
        "decision_id": decision_id,
        "decision_kind": CABINET_LEVEL_AGGREGATE,
        "aggregate_quantity_per_cabinet": decision.get(
            "aggregate_quantity_per_cabinet"
        ),
        "applies_once_per_cabinet": True,
        "multiply_by_member_count": False,
    }
    if source_quantity != expected_quantity:
        raise BridgeError(f"aggregate quantity semantics mismatch for {decision_id}")
    component_qty = require_positive_int(
        source_quantity.get("aggregate_quantity_per_cabinet"),
        f"{decision_id} aggregate_quantity_per_cabinet",
    )
    if (
        decision.get("applies_once_per_cabinet") is not True
        or decision.get("multiply_by_member_count") is not False
    ):
        raise BridgeError(f"aggregate source semantics mismatch for {decision_id}")

    approved_signature = copy.deepcopy(
        dict(
            require_mapping(
                first.get("approved_signature"),
                f"{first_id} approved_signature",
            )
        )
    )
    cabinet_template = first_binding.cabinet_template
    component_ids: list[str] = []
    for component in components:
        component_id = require_non_empty_string(
            component.get("component_evidence_id"),
            "aggregate component_evidence_id",
        )
        if component_id in component_ids:
            raise BridgeError(f"duplicate aggregate member {component_id}")
        binding = bindings.get(component_id)
        if binding is None:
            raise BridgeError(f"missing v0.22 prior binding for {component_id}")
        if (
            binding.decision_kind != CABINET_LEVEL_AGGREGATE
            or binding.decision.get("decision_id") != decision_id
        ):
            raise BridgeError(
                f"ambiguous aggregate decision binding for {component_id}"
            )
        if binding.cabinet_template != cabinet_template:
            raise BridgeError(f"aggregate cabinet group mismatch for {decision_id}")
        if component.get("quantity") != source_quantity:
            raise BridgeError(f"aggregate member quantity mismatch for {decision_id}")
        if component.get("approved_signature") != approved_signature:
            raise BridgeError(f"aggregate member signature mismatch for {decision_id}")
        component_ids.append(component_id)

    expected_member_ids = [
        require_non_empty_string(
            require_mapping(member, "aggregate prior member").get(
                "component_evidence_id"
            ),
            "aggregate prior member.component_evidence_id",
        )
        for member in require_list(decision.get("members"), "aggregate prior members")
    ]
    if len(expected_member_ids) != len(set(expected_member_ids)):
        raise BridgeError(f"duplicate prior aggregate member for {decision_id}")
    if set(component_ids) != set(expected_member_ids):
        raise BridgeError(f"aggregate member coverage mismatch for {decision_id}")

    return {
        "row_id": row_id,
        "cabinet_group_id": template_to_group[cabinet_template],
        "calculator_values": calculator_values(component_qty),
        "source_quantity": source_quantity,
        "source_component_evidence_ids": expected_member_ids,
        "approved_signature": approved_signature,
        "mapping_status": MAPPING_STATUS,
    }


def project_rows_and_groups(
    confirmed: Mapping[str, Any],
    applied: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    installed = require_list(
        confirmed.get("installed_components"),
        "installed_components",
    )
    reserved = require_list(
        confirmed.get("reserved_meter_spaces"),
        "reserved_meter_spaces",
    )
    bindings = build_prior_bindings(applied)
    template_to_group, ordered_templates = cabinet_group_ids(installed, bindings)

    aggregate_components: dict[str, list[Mapping[str, Any]]] = {}
    aggregate_order: list[str] = []
    direct_count = 0
    aggregate_member_count = 0
    for raw_component in installed:
        component = require_mapping(raw_component, "installed component")
        quantity = require_mapping(
            component.get("quantity"),
            "installed component.quantity",
        )
        decision_kind = quantity.get("decision_kind")
        if decision_kind == DIRECT_COMPONENT_QUANTITY:
            direct_count += 1
        elif decision_kind == CABINET_LEVEL_AGGREGATE:
            aggregate_member_count += 1
            decision_id = require_non_empty_string(
                quantity.get("decision_id"),
                "aggregate quantity.decision_id",
            )
            if decision_id not in aggregate_components:
                aggregate_order.append(decision_id)
                aggregate_components[decision_id] = []
            aggregate_components[decision_id].append(component)
        else:
            raise BridgeError("installed component has unsupported decision_kind")

    rows: list[dict[str, Any]] = []
    emitted_aggregates: set[str] = set()
    for raw_component in installed:
        component = require_mapping(raw_component, "installed component")
        component_id = require_non_empty_string(
            component.get("component_evidence_id"),
            "installed component.component_evidence_id",
        )
        quantity = require_mapping(
            component.get("quantity"),
            f"{component_id} quantity",
        )
        binding = bindings.get(component_id)
        if binding is None:
            raise BridgeError(f"missing v0.22 prior binding for {component_id}")
        row_id = f"ROW-DRAFT-{len(rows) + 1:04d}"
        if quantity.get("decision_kind") == DIRECT_COMPONENT_QUANTITY:
            component_qty = verify_direct_quantity(
                component_id,
                quantity,
                binding,
            )
            rows.append(
                {
                    "row_id": row_id,
                    "cabinet_group_id": template_to_group[binding.cabinet_template],
                    "calculator_values": calculator_values(component_qty),
                    "source_quantity": copy.deepcopy(dict(quantity)),
                    "source_component_evidence_ids": [component_id],
                    "approved_signature": copy.deepcopy(
                        dict(
                            require_mapping(
                                component.get("approved_signature"),
                                f"{component_id} approved_signature",
                            )
                        )
                    ),
                    "mapping_status": MAPPING_STATUS,
                }
            )
            continue

        decision_id = require_non_empty_string(
            quantity.get("decision_id"),
            f"{component_id} quantity.decision_id",
        )
        if decision_id in emitted_aggregates:
            continue
        rows.append(
            aggregate_row(
                decision_id,
                aggregate_components[decision_id],
                bindings,
                template_to_group,
                row_id,
            )
        )
        emitted_aggregates.add(decision_id)

    if set(bindings) != {
        require_non_empty_string(
            require_mapping(component, "installed component").get(
                "component_evidence_id"
            ),
            "installed component.component_evidence_id",
        )
        for component in installed
    }:
        raise BridgeError("v0.22 installed binding coverage mismatch")

    reserved_ids = {
        require_non_empty_string(
            require_mapping(item, "reserved meter space").get("component_evidence_id"),
            "reserved meter space.component_evidence_id",
        )
        for item in reserved
    }
    priced_ids = {
        component_id
        for row in rows
        for component_id in cast(list[str], row["source_component_evidence_ids"])
    }
    if reserved_ids & priced_ids:
        raise BridgeError("reserved meter space leaked into pricing row drafts")

    row_ids_by_group: dict[str, list[str]] = {
        group_id: [] for group_id in template_to_group.values()
    }
    for row in rows:
        row_ids_by_group[cast(str, row["cabinet_group_id"])].append(
            cast(str, row["row_id"])
        )
    cabinet_groups = [
        {
            "cabinet_group_id": template_to_group[template],
            "source_cabinet_template": template,
            "product_name": None,
            "cabinet_code": None,
            "cabinet_label": None,
            "consumables_factor": None,
            "mapping_status": MAPPING_STATUS,
            "row_draft_ids": row_ids_by_group[template_to_group[template]],
        }
        for template in ordered_templates
    ]

    coverage = {
        "installed_component_count": len(installed),
        "direct_installed_component_count": direct_count,
        "aggregate_member_count": aggregate_member_count,
        "aggregate_decision_count": len(aggregate_order),
        "pricing_row_draft_count": len(rows),
        "cabinet_group_count": len(cabinet_groups),
        "reserved_meter_space_count": len(reserved),
        "reserved_excluded_from_pricing_count": len(reserved_ids),
        "correction_count": sum(
            require_mapping(component, "installed component").get("overlay_kind")
            == CORRECTION
            for component in installed
        ),
        "reconfirmation_count": sum(
            require_mapping(component, "installed component").get("overlay_kind")
            == RECONFIRMATION
            for component in installed
        ),
    }
    if direct_count + aggregate_member_count != len(installed):
        raise BridgeError("installed component coverage mismatch")
    if len(rows) != direct_count + len(aggregate_order):
        raise BridgeError("row draft coverage mismatch")
    return rows, cabinet_groups, coverage


def build_output_payload(
    confirmed: Mapping[str, Any],
    snapshot: Any,
    confirmed_sha256: str,
) -> dict[str, Any]:
    rows, cabinet_groups, coverage = project_rows_and_groups(
        confirmed,
        snapshot.data,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "draft_type": DRAFT_TYPE,
        "source": {
            "project_id": confirmed["project_id"],
            "confirmation_id": confirmed["confirmation_id"],
            "confirmed_composition_schema_version": CONFIRMED_SCHEMA_VERSION,
            "confirmed_composition_sha256": confirmed_sha256,
            "applied_bundle_schema_version": APPLIED_SCHEMA_VERSION,
            "applied_bundle_sha256": snapshot.sha256,
            "applied_source_lineage": copy.deepcopy(snapshot.data["source_lineage"]),
        },
        "cabinet_groups": cabinet_groups,
        "calculator_input_format": {
            "kind": CSV_KIND,
            "delimiter": CSV_DELIMITER,
            "columns": list(CALCULATOR_COLUMNS),
            "row_drafts": rows,
        },
        "coverage": coverage,
        "safety": {field_name: False for field_name in SAFETY_FIELDS},
        "next_required_human_actions": list(NEXT_REQUIRED_HUMAN_ACTIONS),
    }
    validate_output_payload(payload)
    return payload


def validate_output_payload(payload: Mapping[str, Any]) -> None:
    if set(payload) != ROOT_FIELDS:
        raise BridgeError("output root fields mismatch")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("draft_type") != DRAFT_TYPE
    ):
        raise BridgeError("output schema constants mismatch")

    source = require_mapping(payload.get("source"), "source")
    if set(source) != SOURCE_FIELDS:
        raise BridgeError("output source fields mismatch")
    for field_name in (
        "project_id",
        "confirmation_id",
        "confirmed_composition_sha256",
        "applied_bundle_sha256",
    ):
        require_non_empty_string(source.get(field_name), f"source.{field_name}")
    if (
        source.get("confirmed_composition_schema_version") != CONFIRMED_SCHEMA_VERSION
        or source.get("applied_bundle_schema_version") != APPLIED_SCHEMA_VERSION
    ):
        raise BridgeError("output source schema lineage mismatch")
    require_mapping(source.get("applied_source_lineage"), "applied_source_lineage")

    groups = require_list(payload.get("cabinet_groups"), "cabinet_groups")
    if not groups:
        raise BridgeError("cabinet_groups must be non-empty")
    group_ids: set[str] = set()
    group_row_ids: list[str] = []
    for raw_group in groups:
        group = require_mapping(raw_group, "cabinet group")
        if set(group) != CABINET_GROUP_FIELDS:
            raise BridgeError("cabinet group fields mismatch")
        group_id = require_non_empty_string(
            group.get("cabinet_group_id"),
            "cabinet_group_id",
        )
        require_non_empty_string(
            group.get("source_cabinet_template"),
            "source_cabinet_template",
        )
        if group_id in group_ids:
            raise BridgeError("duplicate cabinet_group_id")
        group_ids.add(group_id)
        for field_name in (
            "product_name",
            "cabinet_code",
            "cabinet_label",
            "consumables_factor",
        ):
            if group.get(field_name) is not None:
                raise BridgeError(f"cabinet group {field_name} must be null")
        if group.get("mapping_status") != MAPPING_STATUS:
            raise BridgeError("cabinet group mapping_status mismatch")
        for row_id in require_list(group.get("row_draft_ids"), "row_draft_ids"):
            group_row_ids.append(
                require_non_empty_string(row_id, "cabinet group row_id")
            )

    calculator_format = require_mapping(
        payload.get("calculator_input_format"),
        "calculator_input_format",
    )
    if set(calculator_format) != FORMAT_FIELDS:
        raise BridgeError("calculator_input_format fields mismatch")
    if (
        calculator_format.get("kind") != CSV_KIND
        or calculator_format.get("delimiter") != CSV_DELIMITER
        or calculator_format.get("columns") != list(CALCULATOR_COLUMNS)
    ):
        raise BridgeError("calculator_input_format constants mismatch")
    rows = require_list(calculator_format.get("row_drafts"), "row_drafts")
    if not rows:
        raise BridgeError("row_drafts must be non-empty")
    row_ids: list[str] = []
    direct_count = 0
    aggregate_member_count = 0
    aggregate_decision_count = 0
    installed_ids: list[str] = []
    for raw_row in rows:
        row = require_mapping(raw_row, "row draft")
        if set(row) != ROW_FIELDS:
            raise BridgeError("row draft fields mismatch")
        row_id = require_non_empty_string(row.get("row_id"), "row_id")
        row_ids.append(row_id)
        if row.get("cabinet_group_id") not in group_ids:
            raise BridgeError("row draft references unknown cabinet group")
        if row.get("mapping_status") != MAPPING_STATUS:
            raise BridgeError("row draft mapping_status mismatch")
        values = require_mapping(row.get("calculator_values"), "calculator_values")
        if set(values) != CALCULATOR_VALUE_FIELDS:
            raise BridgeError("calculator_values fields mismatch")
        require_positive_int(values.get("component_qty"), "component_qty")
        for field_name in CALCULATOR_COLUMNS:
            if field_name != "component_qty" and values.get(field_name) is not None:
                raise BridgeError(f"calculator value {field_name} must be null")
        quantity = require_mapping(row.get("source_quantity"), "source_quantity")
        kind = quantity.get("decision_kind")
        source_ids = [
            require_non_empty_string(item, "source_component_evidence_id")
            for item in require_list(
                row.get("source_component_evidence_ids"),
                "source_component_evidence_ids",
            )
        ]
        if not source_ids or len(source_ids) != len(set(source_ids)):
            raise BridgeError("row source COMP coverage must be non-empty and unique")
        installed_ids.extend(source_ids)
        if kind == DIRECT_COMPONENT_QUANTITY:
            direct_count += 1
            if (
                set(quantity)
                != {"decision_id", "decision_kind", "quantity_per_cabinet"}
                or len(source_ids) != 1
                or values["component_qty"] != quantity["quantity_per_cabinet"]
            ):
                raise BridgeError("direct row quantity semantics mismatch")
        elif kind == CABINET_LEVEL_AGGREGATE:
            aggregate_member_count += len(source_ids)
            aggregate_decision_count += 1
            if (
                set(quantity)
                != {
                    "decision_id",
                    "decision_kind",
                    "aggregate_quantity_per_cabinet",
                    "applies_once_per_cabinet",
                    "multiply_by_member_count",
                }
                or quantity.get("applies_once_per_cabinet") is not True
                or quantity.get("multiply_by_member_count") is not False
                or values["component_qty"] != quantity["aggregate_quantity_per_cabinet"]
            ):
                raise BridgeError("aggregate row quantity semantics mismatch")
        else:
            raise BridgeError("row draft has unsupported quantity semantics")
        require_mapping(row.get("approved_signature"), "approved_signature")

    if len(row_ids) != len(set(row_ids)):
        raise BridgeError("duplicate row_id")
    if sorted(row_ids) != sorted(group_row_ids):
        raise BridgeError("cabinet group row coverage mismatch")
    if len(installed_ids) != len(set(installed_ids)):
        raise BridgeError("installed COMP appears in more than one row")

    coverage = require_mapping(payload.get("coverage"), "coverage")
    if set(coverage) != COVERAGE_FIELDS:
        raise BridgeError("coverage fields mismatch")
    expected_counts = {
        "installed_component_count": len(installed_ids),
        "direct_installed_component_count": direct_count,
        "aggregate_member_count": aggregate_member_count,
        "aggregate_decision_count": aggregate_decision_count,
        "pricing_row_draft_count": len(rows),
        "cabinet_group_count": len(groups),
    }
    for field_name, expected_value in expected_counts.items():
        if coverage.get(field_name) != expected_value:
            raise BridgeError(f"coverage {field_name} mismatch")
    for field_name in COVERAGE_FIELDS:
        value = coverage.get(field_name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise BridgeError(f"coverage {field_name} must be a non-negative integer")
    if coverage.get("reserved_meter_space_count") != coverage.get(
        "reserved_excluded_from_pricing_count"
    ):
        raise BridgeError("reserved meter space exclusion coverage mismatch")
    if coverage.get("correction_count", 0) + coverage.get(
        "reconfirmation_count", 0
    ) > coverage.get("installed_component_count", 0):
        raise BridgeError("overlay coverage exceeds installed components")

    safety = require_mapping(payload.get("safety"), "safety")
    if set(safety) != SAFETY_FIELDS or any(
        value is not False for value in safety.values()
    ):
        raise BridgeError("all pricing and downstream safety fields must be false")
    if payload.get("next_required_human_actions") != list(NEXT_REQUIRED_HUMAN_ACTIONS):
        raise BridgeError("next_required_human_actions mismatch")


def inputs_are_unchanged(
    result: BuildResult,
    confirmed_sha256: str,
    applied_sha256: str,
) -> bool:
    try:
        current_confirmed = hashlib.sha256(
            result.confirmed_composition_json.read_bytes()
        ).hexdigest()
        current_applied = hashlib.sha256(
            result.applied_bundle_json.read_bytes()
        ).hexdigest()
    except OSError:
        return False
    return current_confirmed == confirmed_sha256 and current_applied == applied_sha256


def write_staging_file(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def publish_payload(
    result: BuildResult,
    payload: Mapping[str, Any],
) -> None:
    staging = result.output_json.with_name(
        f".{result.output_json.name}.staging-{uuid.uuid4().hex}"
    )
    content = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        write_staging_file(staging, content)
        staged, staged_content = load_exact_json(staging, "staged output JSON")
        validate_output_payload(staged)
        if staged != payload or staged_content != content:
            raise BridgeError("staged output verification mismatch")
        if result.output_json.exists():
            raise BridgeError("output appeared before publication; overwrite blocked")
        os.rename(staging, result.output_json)
    except BridgeError:
        raise
    except OSError as exc:
        raise BridgeError(f"atomic output publication failed: {exc}") from exc
    finally:
        if staging.exists():
            try:
                staging.unlink()
            except OSError:
                pass
    result.output_created = True
    result.checks["atomic no-overwrite publication"] = "pass"


def build_price_calculator_input_draft_v02(
    confirmed_composition_json: Path,
    applied_bundle_json: Path,
    output_json: Path,
) -> BuildResult:
    result = BuildResult(
        confirmed_composition_json=resolved(confirmed_composition_json),
        applied_bundle_json=resolved(applied_bundle_json),
        output_json=resolved(output_json),
    )
    try:
        validate_output_policy(result)
        confirmed, snapshot, confirmed_sha256 = validate_sources(result)
        payload = build_output_payload(confirmed, snapshot, confirmed_sha256)
        result.checks["quantity and cabinet projection"] = "pass"
        result.checks["in-memory output validation"] = "pass"
        result.checks["safety boundary"] = "pass"
        if not inputs_are_unchanged(
            result,
            confirmed_sha256,
            snapshot.sha256,
        ):
            raise BridgeError("input drift detected before publication")
        result.checks["input drift"] = "pass"
        publish_payload(result, payload)
    except BridgeError as exc:
        add_red_flag(result, str(exc))
        return result

    if all(value == "pass" for value in result.checks.values()):
        result.status = "PASS"
    return result


def format_items(values: Sequence[str]) -> list[str]:
    return list(values) if values else ["none"]


def format_report(result: BuildResult) -> str:
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
            "Output:",
            str(result.output_json) if result.output_created else "not created",
            "",
            "Safety:",
            (
                "no price calculated; all pricing, commercial, sending, "
                "production, and downstream authorizations remain false"
            ),
            "",
            REPORT_END,
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_price_calculator_input_draft_v02(
        args.confirmed_composition_json,
        args.applied_bundle_json,
        args.output_json,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
