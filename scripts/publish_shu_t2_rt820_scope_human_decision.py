"""Publish the exact project-2024/086 SHU-T2 RT-820 Human Decision.

This case-scoped writer records one immutable decision artifact.  It does not
apply the decision, build a successor, calculate a price, or authorize any
downstream action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "technical_shu_t2_rt820_scope_human_decision.v0.1"
SCHEMA_FILENAME = "technical_shu_t2_rt820_scope_human_decision_v0_1.schema.json"
OUTPUT_FILENAME = "technical-shu-t2-rt820-scope-human-decision-v0.1.json"
PROJECT_ID = "2024/086"
DECISION_ID = "IGOR-SHU-T2-RT820-SCOPE-2024-086-001"
STATUS = "IGOR_SHU_T2_RT820_SCOPE_APPROVED_NOT_APPLIED"
AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
APPLICATION_STATUS = "NOT_APPLIED"
PUBLICATION_AUTHORIZATION = (
    "IGOR_SHU_T2_RT820_SCOPE_HUMAN_DECISION_PUBLICATION_AUTHORIZED"
)
REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / SCHEMA_FILENAME
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
CREATED_AT_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")

CANONICAL_LINEAGE_SHA256 = (
    "41ca4e3b63433c8f06c7630565c3d5d5380659e49027bf091a6aff6ab007123e"
)
APPLIED_LINEAGE_SHA256 = (
    "6433e862c7281ac699a12b81e30a02e7f45702ddab22441efd2c79d36589dd6f"
)
CURRENT_SHU_T2_FINGERPRINT = (
    "99db78a5c3c7688a9e2cebbbe57f41489af797bbc61f2b1fa38492a42329cb79"
)
CURRENT_SHU_T1_FINGERPRINT = (
    "4b5cf23236653dfd33e27eefa8034ad2a779b5e2b40f0adc972ee49912dbc0ec"
)

POSITION_SCOPE = (
    ("10", "TFE-016", "PRICE-POSITION-009", "COMP-031", "COMP-034"),
    ("12", "TFE-041", "PRICE-POSITION-023", "COMP-085", "COMP-088"),
    ("14", "TFE-061", "PRICE-POSITION-035", "COMP-128", "COMP-131"),
    ("16", "TFE-083", "PRICE-POSITION-047", "COMP-178", "COMP-181"),
)
SHU_T2_ROW_CONTRACTS = (
    ("ROW-DRAFT-0020", "EKF-VA47-29-2P", "modular_2p", "COMP-033"),
    ("ROW-DRAFT-0021", "EKF-VA47-29-2P", "modular_2p", "COMP-087"),
    ("ROW-DRAFT-0022", "EKF-VA47-29-2P", "modular_2p", "COMP-130"),
    ("ROW-DRAFT-0023", "EKF-VA47-29-2P", "modular_2p", "COMP-180"),
    (
        "ROW-DRAFT-0024",
        "EKF-AD12-1P-N-C16-30MA-4P5KA",
        "diff_1p_n",
        "COMP-032",
    ),
    (
        "ROW-DRAFT-0025",
        "EKF-AD12-1P-N-C16-30MA-4P5KA",
        "diff_1p_n",
        "COMP-086",
    ),
    (
        "ROW-DRAFT-0026",
        "EKF-AD12-1P-N-C16-30MA-4P5KA",
        "diff_1p_n",
        "COMP-129",
    ),
    (
        "ROW-DRAFT-0027",
        "EKF-AD12-1P-N-C16-30MA-4P5KA",
        "diff_1p_n",
        "COMP-179",
    ),
)
SHU_T1_ROW_CODES = {
    "ROW-DRAFT-0110": "EKF-RT-820",
    "ROW-DRAFT-0111": "EKF-AD12-1P-N-C16-30MA-4P5KA",
    "ROW-DRAFT-0112": "EKF-VA47-29-2P",
}
SHU_T1_PRICING_POSITIONS = (
    "PRICE-POSITION-052",
    "PRICE-POSITION-053",
    "PRICE-POSITION-054",
    "PRICE-POSITION-055",
)

INPUT_IDENTITIES = {
    "technical_successor": (
        "price_calculator_input_draft.v0.2",
        "V02_TECHNICAL_COMPLETION_APPLIED_NOT_PRICED",
        "PRICE-CALCULATOR-INPUT-V0.2-ADDITIVE-SUCCESSOR",
    ),
    "composition_decision": (
        "technical_shu_t1_composition_human_decisions.v0.1",
        "IGOR_SHU_T1_COMPOSITION_APPROVED_NOT_APPLIED",
        "IGOR-SHU-T1-COMPOSITION-2024-086-001",
    ),
    "cabinet_pricing_decision": (
        "technical_shu_t1_cabinet_pricing_human_decisions.v0.1",
        "APPROVED_NOT_APPLIED",
        "IGOR-SHU-T1-CABINET-PRICING-2024-086-001",
    ),
    "rt820_code_install_decision": (
        "technical_rt820_code_install_human_decisions.v0.1",
        "IGOR_RT820_CODE_INSTALL_APPROVED_NOT_APPLIED",
        "IGOR-RT820-CODE-INSTALL-2024-086-001",
    ),
    "pricing_profile": (
        "technical_invoice519_pricing_profile_human_decisions.v0.1",
        "IGOR_INVOICE519_PRICING_PROFILE_APPROVED_NOT_APPLIED",
        "IGOR-INVOICE519-PRICING-PROFILE-2024-086-001",
    ),
}


class ContractError(ValueError):
    """An input, payload, schema, or publication boundary failed closed."""


@dataclass(frozen=True)
class InputPaths:
    technical_successor: Path
    composition_decision: Path
    cabinet_pricing_decision: Path
    rt820_code_install_decision: Path
    pricing_profile: Path


@dataclass(frozen=True)
class ExpectedShas:
    technical_successor: str
    composition_decision: str
    cabinet_pricing_decision: str
    rt820_code_install_decision: str
    pricing_profile: str


@dataclass(frozen=True)
class LoadedInput:
    role: str
    path: Path
    expected_sha256: str
    raw: bytes
    value: dict[str, Any]


@dataclass(frozen=True)
class PublicationResult:
    sha256: str
    size: int
    encoded: bytes


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path, description: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read {description}: {path}: {exc}") from exc
    try:
        value = json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid {description}: {path}: {exc}") from exc
    require(isinstance(value, dict), f"{description} root must be an object")
    return value, raw


def require_mapping(value: Any, description: str) -> Mapping[str, Any]:
    require(isinstance(value, Mapping), f"{description} must be an object")
    return value


def require_list(value: Any, description: str) -> list[Any]:
    require(isinstance(value, list), f"{description} must be an array")
    return value


def require_exact_booleans(
    value: Any, expected: Mapping[str, bool], description: str
) -> None:
    mapping = require_mapping(value, description)
    require(set(mapping) == set(expected), f"{description} keys mismatch")
    for key, expected_value in expected.items():
        require(type(mapping[key]) is bool, f"{description}.{key} must be boolean")
        require(mapping[key] is expected_value, f"{description}.{key} mismatch")


def authority_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get("authority")
    return value


def validate_sha256(value: str, description: str) -> None:
    require(
        isinstance(value, str) and SHA256_RE.fullmatch(value) is not None,
        f"{description} SHA-256 must be 64 lowercase hexadecimal characters",
    )


def _decision_identity(
    value: Mapping[str, Any], role: str, expected_path: Path, expected_sha: str
) -> None:
    schema, status, decision_id = INPUT_IDENTITIES[role]
    require(value.get("schema_version") == schema, f"{role} schema mismatch")
    require(value.get("project_id") == PROJECT_ID, f"{role} project mismatch")
    require(value.get("status") == status, f"{role} status mismatch")
    require(value.get("decision_id") == decision_id, f"{role} decision ID mismatch")
    require(authority_value(value.get("authority")) == AUTHORITY, f"{role} authority")
    require(
        value.get("application_status") == APPLICATION_STATUS,
        f"{role} application status mismatch",
    )
    require(value.get("scope_expansion") is False, f"{role} scope expansion")
    require(value.get("immutable") is True, f"{role} immutable mismatch")
    require(value.get("no_overwrite") is True, f"{role} no-overwrite mismatch")
    validate_sha256(expected_sha, role)
    require(expected_path.is_file(), f"{role} path is not an existing file")


def _find_exactly_one(
    values: Sequence[Any], key: str, expected: str, description: str
) -> Mapping[str, Any]:
    matches = [
        item
        for item in values
        if isinstance(item, Mapping) and item.get(key) == expected
    ]
    require(len(matches) == 1, f"{description} requires exactly one {expected}")
    return matches[0]


def _validate_direct_bindings(
    technical: Mapping[str, Any], paths: InputPaths, shas: ExpectedShas
) -> None:
    source = require_mapping(technical.get("source"), "technical source")
    require(source.get("project_id") == PROJECT_ID, "technical project mismatch")
    require(
        source.get("applied_bundle_sha256") == APPLIED_LINEAGE_SHA256,
        "applied lineage SHA mismatch",
    )
    lineage = require_mapping(
        source.get("applied_source_lineage"), "technical applied lineage"
    )
    require(
        lineage.get("canonical_replay_sha256") == CANONICAL_LINEAGE_SHA256,
        "canonical lineage SHA mismatch",
    )
    additive = require_mapping(
        source.get("additive_completed_input_successor"),
        "technical additive successor",
    )
    require(additive.get("project_id") == PROJECT_ID, "additive project mismatch")
    require(additive.get("scope_expansion") is False, "additive scope expansion")
    bindings = require_list(
        additive.get("direct_human_decision_inputs"), "technical decision bindings"
    )
    expected = (
        (
            "technical_composition_human_decision",
            paths.composition_decision,
            shas.composition_decision,
            "composition_decision",
        ),
        (
            "cabinet_pricing_human_decision",
            paths.cabinet_pricing_decision,
            shas.cabinet_pricing_decision,
            "cabinet_pricing_decision",
        ),
        (
            "rt820_code_install_human_decision",
            paths.rt820_code_install_decision,
            shas.rt820_code_install_decision,
            "rt820_code_install_decision",
        ),
    )
    require(len(bindings) == len(expected), "technical decision binding count mismatch")
    for binding, (binding_role, path, sha, identity_role) in zip(
        bindings, expected, strict=True
    ):
        mapping = require_mapping(binding, f"technical binding {binding_role}")
        schema, status, decision_id = INPUT_IDENTITIES[identity_role]
        require(
            mapping
            == {
                "role": binding_role,
                "path": str(path),
                "sha256": sha,
                "schema_version": schema,
                "status": status,
                "decision_id": decision_id,
                "authority": AUTHORITY,
                "application_status": APPLICATION_STATUS,
            },
            f"technical binding mismatch: {binding_role}",
        )


def _validate_shu_t2_technical(technical: Mapping[str, Any]) -> None:
    groups = require_list(technical.get("cabinet_groups"), "technical groups")
    group = _find_exactly_one(
        groups, "cabinet_group_id", "CABINET-GROUP-003", "technical groups"
    )
    expected_row_ids = [item[0] for item in SHU_T2_ROW_CONTRACTS]
    require(group.get("product_name") == "ШУ-Т2", "SHU-T2 product mismatch")
    require(group.get("cabinet_code") == "CAB-KRN-12", "SHU-T2 cabinet mismatch")
    require(
        group.get("row_draft_ids") == expected_row_ids,
        "SHU-T2 technical row IDs mismatch",
    )
    calculator = require_mapping(
        technical.get("calculator_input_format"), "technical calculator format"
    )
    rows = require_list(calculator.get("row_drafts"), "technical row drafts")
    group_rows = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and row.get("cabinet_group_id") == "CABINET-GROUP-003"
    ]
    require(len(group_rows) == 8, "SHU-T2 must have exactly eight current rows")
    for row_id, component_code, install_type, evidence_id in SHU_T2_ROW_CONTRACTS:
        row = _find_exactly_one(group_rows, "row_id", row_id, "SHU-T2 rows")
        values = require_mapping(row.get("calculator_values"), f"{row_id} values")
        require(values.get("product_name") == "ШУ-Т2", f"{row_id} product mismatch")
        require(values.get("cabinet_code") == "CAB-KRN-12", f"{row_id} cabinet")
        require(values.get("component_code") == component_code, f"{row_id} code")
        require(values.get("component_qty") == 1, f"{row_id} quantity")
        require(values.get("install_type") == install_type, f"{row_id} install")
        require(
            row.get("source_component_evidence_ids") == [evidence_id],
            f"{row_id} evidence mismatch",
        )
    require(
        all(
            require_mapping(row.get("calculator_values"), "SHU-T2 values").get(
                "component_code"
            )
            != "EKF-RT-820"
            for row in group_rows
        ),
        "current SHU-T2 already contains RT-820",
    )


def _validate_shu_t1_technical(technical: Mapping[str, Any]) -> None:
    groups = require_list(technical.get("cabinet_groups"), "technical groups")
    group = _find_exactly_one(
        groups, "cabinet_group_id", "CABINET-GROUP-015", "technical groups"
    )
    require(group.get("product_name") == "ШУ-Т1", "SHU-T1 product changed")
    require(group.get("cabinet_code") == "CAB-KRN-12", "SHU-T1 cabinet changed")
    require(
        group.get("row_draft_ids") == list(SHU_T1_ROW_CODES),
        "SHU-T1 row IDs changed",
    )
    calculator = require_mapping(
        technical.get("calculator_input_format"), "technical calculator format"
    )
    rows = require_list(calculator.get("row_drafts"), "technical row drafts")
    for row_id, component_code in SHU_T1_ROW_CODES.items():
        row = _find_exactly_one(rows, "row_id", row_id, "SHU-T1 rows")
        require(row.get("cabinet_group_id") == "CABINET-GROUP-015", "SHU-T1 group")
        values = require_mapping(row.get("calculator_values"), f"{row_id} values")
        require(values.get("product_name") == "ШУ-Т1", "SHU-T1 row product changed")
        require(values.get("component_code") == component_code, "SHU-T1 row changed")


def validate_technical_successor(
    technical: Mapping[str, Any], paths: InputPaths, shas: ExpectedShas
) -> None:
    require(
        technical.get("schema_version") == INPUT_IDENTITIES["technical_successor"][0],
        "technical successor schema mismatch",
    )
    completion = require_mapping(technical.get("completion"), "technical completion")
    require(
        completion.get("status") == INPUT_IDENTITIES["technical_successor"][1],
        "technical successor status mismatch",
    )
    require_exact_booleans(
        technical.get("safety"),
        {
            "price_approved_by_igor": False,
            "production_authorized": False,
            "pricing_started": False,
            "downstream_started": False,
            "sending_authorized": False,
            "commercial_csv_authorized": False,
            "price_calculation_executed": False,
        },
        "technical safety",
    )
    _validate_direct_bindings(technical, paths, shas)
    _validate_shu_t2_technical(technical)
    _validate_shu_t1_technical(technical)


def validate_rt820_decision(value: Mapping[str, Any]) -> None:
    contract = require_mapping(
        value.get("approved_code_install_contract"), "RT-820 code/install contract"
    )
    require(
        contract
        == {
            "manufacturer": "EKF",
            "product": "Реле температуры RT-820 EKF PROxima",
            "manufacturer_article": "RT-820",
            "supply_form": (
                "ONE_TEMPERATURE_RELAY_WITH_ONE_EXTERNAL_TEMPERATURE_SENSOR"
            ),
            "internal_component_code": "EKF-RT-820",
            "install_type": "temperature_relay_din_2mod",
            "module_width_din": 2,
            "quantity_per_individual_cabinet": 1,
            "unit": "комплект",
            "decision_status": "APPROVED_NOT_APPLIED",
            "application_status": "NOT_APPLIED",
        },
        "RT-820 code/install contract mismatch",
    )
    pricing = require_mapping(
        value.get("pricing_work_semantics"), "RT-820 pricing/work semantics"
    )
    expected_pricing = {
        "workbook_label_source": "КРН!A19",
        "workbook_label": "Терморегулятор RT-820",
        "material_source": "КРН!B19",
        "material_price_kzt_per_complete_set": 15000,
        "work_source": "КРН!C19",
        "work_price_kzt_per_complete_set": 900,
        "work_price_semantics": "EXACT_COMPONENT_WORK_PRICE",
        "generic_modular_2p_work_price_kzt": 432,
        "generic_modular_2p_work_price_prohibited": True,
        "similar_relay_price_fallback_prohibited": True,
        "family_fallback_prohibited": True,
        "fuzzy_fallback_prohibited": True,
        "price_does_not_create_technical_identity": True,
    }
    require(pricing == expected_pricing, "RT-820 pricing/work or fallback mismatch")
    bundle = require_mapping(
        value.get("tst05_bundle_semantics"), "RT-820 TST05 bundle semantics"
    )
    require(bundle.get("separate_component_row") is False, "separate TST05 row")
    require(bundle.get("separate_material_charge") is False, "separate TST05 material")
    require(bundle.get("separate_work_charge") is False, "separate TST05 work")
    require(bundle.get("separate_pricing_row") is False, "separate TST05 pricing")


def _validate_profile_bindings(
    profile: Mapping[str, Any], paths: InputPaths, shas: ExpectedShas
) -> None:
    bindings = require_list(
        profile.get("authoritative_inputs"), "pricing profile authoritative inputs"
    )
    expected = (
        (
            "completed_technical_input_additive_successor",
            paths.technical_successor,
            shas.technical_successor,
        ),
        (
            "technical_composition_human_decision",
            paths.composition_decision,
            shas.composition_decision,
        ),
        (
            "cabinet_pricing_human_decision",
            paths.cabinet_pricing_decision,
            shas.cabinet_pricing_decision,
        ),
        (
            "rt820_code_install_human_decision",
            paths.rt820_code_install_decision,
            shas.rt820_code_install_decision,
        ),
    )
    for role, path, sha in expected:
        binding = _find_exactly_one(bindings, "role", role, "profile bindings")
        require(binding.get("path") == str(path), f"profile {role} path mismatch")
        require(binding.get("sha256") == sha, f"profile {role} SHA mismatch")


def _validate_shu_t2_profile(profile: Mapping[str, Any]) -> None:
    scope = require_mapping(
        profile.get("current_completed_technical_scope"), "profile current scope"
    )
    groups = require_list(scope.get("cabinet_groups"), "profile cabinet groups")
    group = _find_exactly_one(
        groups, "cabinet_group_id", "CABINET-GROUP-003", "profile groups"
    )
    require(group.get("product_name") == "ШУ-Т2", "profile SHU-T2 product mismatch")
    require(group.get("cabinet_code") == "CAB-KRN-12", "profile SHU-T2 cabinet")
    positions = require_list(scope.get("pricing_positions"), "profile positions")
    expected_row_pairs = (
        ["ROW-DRAFT-0020", "ROW-DRAFT-0024"],
        ["ROW-DRAFT-0021", "ROW-DRAFT-0025"],
        ["ROW-DRAFT-0022", "ROW-DRAFT-0026"],
        ["ROW-DRAFT-0023", "ROW-DRAFT-0027"],
    )
    for contract, row_ids in zip(POSITION_SCOPE, expected_row_pairs, strict=True):
        section, technical_id, pricing_id, _relay, _sensor = contract
        position = _find_exactly_one(
            positions, "pricing_position_id", pricing_id, "profile SHU-T2 positions"
        )
        require(position.get("section") == section, f"{pricing_id} section mismatch")
        require(
            position.get("source_position_id") == technical_id,
            f"{pricing_id} technical position mismatch",
        )
        require(position.get("product_name") == "ШУ-Т2", f"{pricing_id} product")
        require(
            position.get("cabinet_group_id") == "CABINET-GROUP-003",
            f"{pricing_id} group",
        )
        require(position.get("cabinet_code") == "CAB-KRN-12", f"{pricing_id} cabinet")
        require(
            position.get("physical_multiplicity") == 1,
            f"{pricing_id} multiplicity",
        )
        require(position.get("row_draft_ids") == row_ids, f"{pricing_id} rows")
        require(
            position.get("composition_fingerprint_sha256")
            == CURRENT_SHU_T2_FINGERPRINT,
            f"{pricing_id} fingerprint",
        )
    actual_ids = {
        item.get("pricing_position_id")
        for item in positions
        if isinstance(item, Mapping) and item.get("product_name") == "ШУ-Т2"
    }
    require(
        actual_ids == {item[2] for item in POSITION_SCOPE},
        "missing or extra SHU-T2 pricing position",
    )


def _validate_shu_t1_profile(profile: Mapping[str, Any]) -> None:
    scope = require_mapping(
        profile.get("current_completed_technical_scope"), "profile current scope"
    )
    groups = require_list(scope.get("cabinet_groups"), "profile cabinet groups")
    group = _find_exactly_one(
        groups, "cabinet_group_id", "CABINET-GROUP-015", "profile groups"
    )
    require(group.get("product_name") == "ШУ-Т1", "profile SHU-T1 product changed")
    require(group.get("cabinet_code") == "CAB-KRN-12", "profile SHU-T1 cabinet changed")
    require(
        group.get("row_draft_ids") == list(SHU_T1_ROW_CODES),
        "profile SHU-T1 rows changed",
    )
    positions = require_list(scope.get("pricing_positions"), "profile positions")
    actual = [
        item
        for item in positions
        if isinstance(item, Mapping) and item.get("product_name") == "ШУ-Т1"
    ]
    require(len(actual) == 4, "profile SHU-T1 position count changed")
    require(
        {item.get("pricing_position_id") for item in actual}
        == set(SHU_T1_PRICING_POSITIONS),
        "profile SHU-T1 position IDs changed",
    )
    require(
        all(
            item.get("cabinet_group_id") == "CABINET-GROUP-015"
            and item.get("composition_fingerprint_sha256") == CURRENT_SHU_T1_FINGERPRINT
            and item.get("physical_multiplicity") == 1
            for item in actual
        ),
        "profile SHU-T1 scope changed",
    )


def validate_pricing_profile(
    profile: Mapping[str, Any], paths: InputPaths, shas: ExpectedShas
) -> None:
    schema, status, decision_id = INPUT_IDENTITIES["pricing_profile"]
    require(profile.get("schema_version") == schema, "pricing profile schema mismatch")
    require(profile.get("project_id") == PROJECT_ID, "pricing profile project mismatch")
    require(profile.get("status") == status, "pricing profile status mismatch")
    require(profile.get("decision_id") == decision_id, "pricing profile decision ID")
    require(authority_value(profile.get("authority")) == AUTHORITY, "profile authority")
    require(
        profile.get("application_status") == APPLICATION_STATUS,
        "pricing profile application status",
    )
    require(profile.get("scope_expansion") is False, "pricing profile expansion")
    require_exact_booleans(
        profile.get("safety_flags"),
        {
            "pricing_profile_decision_recorded": True,
            "pricing_profile_applied": False,
            "current_scope_pricing_calculated": False,
            "reserved_formula_rules_applied": False,
            "calculator_run_authorized": False,
            "checked_calculator_run_authorized": False,
            "quote_generation_authorized": False,
            "price_approval_for_client": False,
            "lead_time_approved": False,
            "client_send_authorized": False,
            "procurement_authorized": False,
            "production_authorized": False,
            "scope_expansion": False,
        },
        "pricing profile safety",
    )
    _validate_profile_bindings(profile, paths, shas)
    _validate_shu_t2_profile(profile)
    _validate_shu_t1_profile(profile)


def load_and_validate_inputs(
    paths: InputPaths, shas: ExpectedShas
) -> dict[str, LoadedInput]:
    path_values = vars(paths)
    sha_values = vars(shas)
    require(
        len({Path(value).resolve(strict=False) for value in path_values.values()}) == 5,
        "input paths must be five distinct files",
    )
    loaded: dict[str, LoadedInput] = {}
    for role in INPUT_IDENTITIES:
        path = Path(path_values[role])
        expected_sha = str(sha_values[role])
        validate_sha256(expected_sha, role)
        value, raw = load_json(path, role)
        require(sha256_bytes(raw) == expected_sha, f"initial SHA mismatch: {role}")
        loaded[role] = LoadedInput(role, path, expected_sha, raw, value)

    _decision_identity(
        loaded["composition_decision"].value,
        "composition_decision",
        paths.composition_decision,
        shas.composition_decision,
    )
    _decision_identity(
        loaded["cabinet_pricing_decision"].value,
        "cabinet_pricing_decision",
        paths.cabinet_pricing_decision,
        shas.cabinet_pricing_decision,
    )
    _decision_identity(
        loaded["rt820_code_install_decision"].value,
        "rt820_code_install_decision",
        paths.rt820_code_install_decision,
        shas.rt820_code_install_decision,
    )
    validate_rt820_decision(loaded["rt820_code_install_decision"].value)
    validate_technical_successor(loaded["technical_successor"].value, paths, shas)
    validate_pricing_profile(loaded["pricing_profile"].value, paths, shas)
    return loaded


def _scope_positions() -> list[dict[str, Any]]:
    return [
        {
            "section": section,
            "technical_position_id": technical_id,
            "pricing_position_id": pricing_id,
            "relay_evidence_id": relay_id,
            "sensor_evidence_id": sensor_id,
            "physical_multiplicity": 1,
        }
        for section, technical_id, pricing_id, relay_id, sensor_id in POSITION_SCOPE
    ]


def _input_bindings(loaded: Mapping[str, LoadedInput]) -> list[dict[str, Any]]:
    return [
        {
            "role": role,
            "path": str(loaded[role].path),
            "expected_sha256": loaded[role].expected_sha256,
            "actual_sha256": sha256_bytes(loaded[role].raw),
            "schema_version": INPUT_IDENTITIES[role][0],
            "status": INPUT_IDENTITIES[role][1],
            "artifact_identity": INPUT_IDENTITIES[role][2],
        }
        for role in INPUT_IDENTITIES
    ]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_payload(
    loaded: Mapping[str, LoadedInput], created_at_utc: str | None = None
) -> dict[str, Any]:
    created = created_at_utc or utc_now()
    require(CREATED_AT_RE.fullmatch(created) is not None, "created_at_utc format")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "IMMUTABLE_HUMAN_DECISION_CAPTURE",
        "project_id": PROJECT_ID,
        "decision_id": DECISION_ID,
        "status": STATUS,
        "authority": AUTHORITY,
        "application_status": APPLICATION_STATUS,
        "created_at_utc": created,
        "input_bindings": _input_bindings(loaded),
        "lineage_anchors": {
            "applied_component_lineage_sha256": APPLIED_LINEAGE_SHA256,
            "canonical_position_lineage_sha256": CANONICAL_LINEAGE_SHA256,
        },
        "exact_scope": {
            "product": "ШУ-Т2",
            "cabinet_group_id": "CABINET-GROUP-003",
            "cabinet_code": "CAB-KRN-12",
            "positions": _scope_positions(),
            "source_evidence_row_count": 8,
            "future_component_row_count": 4,
        },
        "rt820_contract": {
            "component_code": "EKF-RT-820",
            "component_qty_per_physical_cabinet": 1,
            "install_type": "temperature_relay_din_2mod",
            "module_width": 2,
            "source_range": "КРН!A19:C19",
            "source_label": "Терморегулятор RT-820",
            "material_kzt": 15000,
            "work_kzt": 900,
            "generic_work_432_prohibited": True,
            "family_fallback_prohibited": True,
            "fuzzy_fallback_prohibited": True,
            "similar_relay_fallback_prohibited": True,
        },
        "bundle_semantics": {
            "relay_and_sensor_form_one_indivisible_complete_set": True,
            "tst05_provenance_only": True,
            "separate_tst05_component_row": False,
            "separate_tst05_material_charge": False,
            "separate_tst05_work_charge": False,
            "separate_tst05_pricing_row": False,
            "double_counting_prohibited": True,
        },
        "supersession": {
            "prior_decision_id": "HDA-019-H19-3",
            "superseded_field": (
                "$.supply_boundary.rt007s_authority_proof.rule_payload."
                "forbidden_transfer_designation"
            ),
            "prior_value": "ШУ-Т2",
            "applies_only_to_evidence_ids": [
                evidence for item in POSITION_SCOPE for evidence in (item[3], item[4])
            ],
            "outside_cabinet_exclusion_count_must_be_derived": True,
            "outside_cabinet_exclusion_count_override_prohibited": True,
            "all_other_supply_boundaries_unchanged": True,
            "all_other_human_decisions_unchanged": True,
            "shu_t1_unchanged": True,
        },
        "shu_t1_integrity": {
            "cabinet_group_id": "CABINET-GROUP-015",
            "technical_row_ids": list(SHU_T1_ROW_CODES),
            "pricing_position_ids": list(SHU_T1_PRICING_POSITIONS),
            "composition_fingerprint_sha256": CURRENT_SHU_T1_FINGERPRINT,
            "byte_and_semantic_change_authorized": False,
        },
        "safety": {
            "human_decision_recorded": True,
            "decision_applied_to_technical_successor": False,
            "decision_applied_to_pricing_profile": False,
            "calculator_run_authorized": False,
            "price_calculated": False,
            "price_approved": False,
            "price_floor_authorized": False,
            "quote_or_invoice_authorized": False,
            "client_send_authorized": False,
            "procurement_authorized": False,
            "production_authorized": False,
            "downstream_authorized": False,
            "scope_expansion": False,
        },
        "publication_control": {
            "immutable": True,
            "no_overwrite": True,
            "atomic_publication": True,
            "input_toctou_recheck_required": True,
            "final_strict_json_reread_required": True,
            "authorization_token_required": True,
        },
    }
    validate_payload(payload)
    return payload


def _schema_type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, Mapping)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return type(value) is int
    if expected_type == "boolean":
        return type(value) is bool
    raise ContractError(f"unsupported schema type: {expected_type}")


def _json_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":")
    )


def validate_against_schema(
    value: Any, schema: Mapping[str, Any], path: str = "$"
) -> None:
    if "const" in schema:
        require(_json_equal(value, schema["const"]), f"schema const mismatch at {path}")
    expected_type = schema.get("type")
    if expected_type is not None:
        require(
            isinstance(expected_type, str)
            and _schema_type_matches(value, expected_type),
            f"schema type mismatch at {path}",
        )
    if "enum" in schema:
        require(
            any(_json_equal(value, candidate) for candidate in schema["enum"]),
            f"schema enum mismatch at {path}",
        )
    if isinstance(value, str):
        if "minLength" in schema:
            require(len(value) >= schema["minLength"], f"schema minLength at {path}")
        if "pattern" in schema:
            require(
                re.search(schema["pattern"], value) is not None,
                f"schema pattern at {path}",
            )
    if isinstance(value, Mapping):
        required = schema.get("required", [])
        require(isinstance(required, list), f"schema required invalid at {path}")
        missing = [key for key in required if key not in value]
        require(not missing, f"schema missing keys at {path}: {missing}")
        properties = schema.get("properties", {})
        require(isinstance(properties, Mapping), f"schema properties invalid at {path}")
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            require(not extra, f"schema extra keys at {path}: {sorted(extra)}")
        for key, child in properties.items():
            if key in value:
                validate_against_schema(
                    value[key],
                    require_mapping(child, f"schema {path}.{key}"),
                    f"{path}.{key}",
                )
    if isinstance(value, list):
        if "minItems" in schema:
            require(len(value) >= schema["minItems"], f"schema minItems at {path}")
        if "maxItems" in schema:
            require(len(value) <= schema["maxItems"], f"schema maxItems at {path}")
        if schema.get("uniqueItems") is True:
            canonical = [json.dumps(item, sort_keys=True) for item in value]
            require(
                len(canonical) == len(set(canonical)),
                f"schema uniqueItems at {path}",
            )
        item_schema = schema.get("items")
        if item_schema is not None:
            mapping = require_mapping(item_schema, f"schema items at {path}")
            for index, item in enumerate(value):
                validate_against_schema(item, mapping, f"{path}[{index}]")


def load_schema() -> dict[str, Any]:
    schema, _raw = load_json(SCHEMA_PATH, "committed decision schema")
    require(
        schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
        "schema dialect mismatch",
    )
    require(schema.get("type") == "object", "schema root type mismatch")
    require(schema.get("additionalProperties") is False, "schema must be closed")
    properties = require_mapping(schema.get("properties"), "schema properties")
    schema_version = require_mapping(
        properties.get("schema_version"), "schema schema_version"
    )
    require(schema_version.get("const") == SCHEMA_VERSION, "schema version contract")
    return schema


def validate_payload(payload: Mapping[str, Any]) -> None:
    schema = load_schema()
    validate_against_schema(payload, schema)
    require(
        [item.get("role") for item in payload["input_bindings"]]
        == list(INPUT_IDENTITIES),
        "input binding role order mismatch",
    )
    for item in payload["input_bindings"]:
        require(
            item.get("actual_sha256") == item.get("expected_sha256"),
            "input binding SHA mismatch",
        )


def serialize(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _path_identity(path: Path) -> tuple[int, int]:
    stat_result = os.lstat(path)
    return stat_result.st_dev, stat_result.st_ino


def _rollback_publication(
    output: Path,
    staging: Path | None,
    final_link_created: bool,
    staged_identity: tuple[int, int] | None,
) -> list[str]:
    blockers: list[str] = []
    if final_link_created and os.path.lexists(output):
        try:
            current_identity = _path_identity(output)
            if staged_identity is None or current_identity != staged_identity:
                blockers.append("foreign final replacement preserved")
            else:
                output.unlink()
        except OSError as exc:
            blockers.append(f"owned final cleanup failed: {exc}")
    if staging is not None and os.path.lexists(staging):
        try:
            staging.unlink()
        except OSError as exc:
            blockers.append(f"staging cleanup failed: {exc}")
    if output.parent.exists():
        try:
            output.parent.rmdir()
        except OSError as exc:
            blockers.append(f"output directory cleanup failed: {exc}")
    return blockers


def publish_decision(
    paths: InputPaths, shas: ExpectedShas, output: Path
) -> PublicationResult:
    require(output.name == OUTPUT_FILENAME, "output filename mismatch")
    require(output.parent != output, "output directory mismatch")
    require(output.parent.parent.is_dir(), "output directory owner must already exist")
    require(not output.parent.exists(), "output directory already exists")
    input_resolved = {path.resolve(strict=False) for path in vars(paths).values()}
    require(
        output.resolve(strict=False) not in input_resolved,
        "output must not alias an input",
    )

    loaded = load_and_validate_inputs(paths, shas)
    payload = build_payload(loaded)
    encoded = serialize(payload)
    output.parent.mkdir()
    descriptor = -1
    staging: Path | None = None
    staged_identity: tuple[int, int] | None = None
    final_link_created = False
    try:
        descriptor, staging_name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".staging", dir=output.parent
        )
        staging = Path(staging_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        staged, staged_raw = load_json(staging, "staged Human Decision")
        require(staged_raw == encoded, "staged bytes mismatch")
        validate_payload(staged)
        require(
            set(output.parent.iterdir()) == {staging},
            "output directory contains unexpected entries before publication",
        )
        for loaded_input in loaded.values():
            try:
                current = loaded_input.path.read_bytes()
            except OSError as exc:
                raise ContractError(
                    f"TOCTOU reread failed: {loaded_input.role}: {exc}"
                ) from exc
            require(
                current == loaded_input.raw,
                f"TOCTOU bytes changed: {loaded_input.role}",
            )
            require(
                sha256_bytes(current) == loaded_input.expected_sha256,
                f"TOCTOU SHA mismatch: {loaded_input.role}",
            )
        require(not output.exists(), "output appeared before publication")
        staged_identity = _path_identity(staging)
        try:
            os.link(staging, output)
        except OSError as exc:
            raise ContractError(
                f"atomic no-overwrite publication failed: {exc}"
            ) from exc
        final_link_created = True
        require(
            _path_identity(output) == staged_identity,
            "published final identity mismatch",
        )
        published, published_raw = load_json(output, "published Human Decision")
        require(published_raw == encoded, "published bytes mismatch")
        validate_payload(published)
        staging.unlink()
        require(
            _path_identity(output) == staged_identity,
            "published final identity changed before success",
        )
        require(
            set(output.parent.iterdir()) == {output},
            "output directory final inventory mismatch",
        )
        return PublicationResult(
            sha256_bytes(published_raw), len(published_raw), encoded
        )
    except BaseException as error:
        blockers: list[str] = []
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                blockers.append(f"staging descriptor cleanup failed: {exc}")
        blockers.extend(
            _rollback_publication(
                output,
                staging,
                final_link_created,
                staged_identity,
            )
        )
        if blockers:
            raise ContractError(
                "publication rollback cleanup blocked: " + "; ".join(blockers)
            ) from error
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--technical-successor", required=True, type=Path)
    parser.add_argument("--technical-successor-sha256", required=True)
    parser.add_argument("--composition-decision", required=True, type=Path)
    parser.add_argument("--composition-decision-sha256", required=True)
    parser.add_argument("--cabinet-pricing-decision", required=True, type=Path)
    parser.add_argument("--cabinet-pricing-decision-sha256", required=True)
    parser.add_argument("--rt820-code-install-decision", required=True, type=Path)
    parser.add_argument("--rt820-code-install-decision-sha256", required=True)
    parser.add_argument("--pricing-profile", required=True, type=Path)
    parser.add_argument("--pricing-profile-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorization", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    require(
        args.authorization == PUBLICATION_AUTHORIZATION,
        "exact SHU-T2 RT-820 Human Decision publication authorization is required",
    )
    paths = InputPaths(
        args.technical_successor,
        args.composition_decision,
        args.cabinet_pricing_decision,
        args.rt820_code_install_decision,
        args.pricing_profile,
    )
    shas = ExpectedShas(
        args.technical_successor_sha256,
        args.composition_decision_sha256,
        args.cabinet_pricing_decision_sha256,
        args.rt820_code_install_decision_sha256,
        args.pricing_profile_sha256,
    )
    result = publish_decision(paths, shas, args.output)
    print(
        f"PUBLISHED_IMMUTABLE_NO_OVERWRITE {args.output} "
        f"SHA256={result.sha256} SIZE={result.size}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
