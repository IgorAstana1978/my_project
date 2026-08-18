"""Build the immutable Invoice 519 pricing-profile successor for ШУ-Т1."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROJECT_ID = "2024/086"
PUBLICATION_AUTHORIZATION = (
    "IGOR_SHU_T1_INVOICE519_PRICING_PROFILE_SUCCESSOR_PUBLICATION_AUTHORIZED"
)
SUCCESSOR_CONTRACT = "controlled_additive_invoice519_pricing_profile_successor.v0.1"
TECHNICAL_SUCCESSOR_CONTRACT = "controlled_additive_completed_input_successor.v0.1"
REPO_ROOT = Path(__file__).resolve().parents[1]

BASE_PROFILE = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-INVOICE519-PRICING-PROFILE-DECISION-20260814-001\technical-invoice519-pricing-profile-human-decisions-v0.1.json"
)
BASE_PROFILE_SHA256 = "60d1f9c794b7d1164feaa20dbfaba6493dac8da480462941c3a6b7e17871c2a8"
COMPOSITION_DECISION = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-SHU-T1-HUMAN-DECISIONS-20260817-001\technical-shu-t1-composition-human-decisions-v0.1.json"
)
COMPOSITION_SHA256 = "bccf62150488037b7df50804c88454119748be103da22dad456db2969126c008"
CABINET_PRICING_DECISION = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-SHU-T1-CABINET-PRICING-DECISION-20260817-001\technical-shu-t1-cabinet-pricing-human-decisions-v0.1.json"
)
CABINET_PRICING_SHA256 = (
    "b3a1bb84bacb2cc5127752cb378b2151552fcb443f02116b12269a086add4247"
)
RT820_DECISION = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-RT820-CODE-INSTALL-DECISION-20260818-001\technical-rt820-code-install-human-decisions-v0.1.json"
)
RT820_SHA256 = "95c9f2610a6e8429242789e17c3b69ffae31db28655736aed12caa1d3939630f"

DECISION_CONTRACTS = (
    (
        "technical_composition_human_decision",
        COMPOSITION_DECISION,
        COMPOSITION_SHA256,
        "technical_shu_t1_composition_human_decisions.v0.1",
        "IGOR_SHU_T1_COMPOSITION_APPROVED_NOT_APPLIED",
        "IGOR-SHU-T1-COMPOSITION-2024-086-001",
    ),
    (
        "cabinet_pricing_human_decision",
        CABINET_PRICING_DECISION,
        CABINET_PRICING_SHA256,
        "technical_shu_t1_cabinet_pricing_human_decisions.v0.1",
        "APPROVED_NOT_APPLIED",
        "IGOR-SHU-T1-CABINET-PRICING-2024-086-001",
    ),
    (
        "rt820_code_install_human_decision",
        RT820_DECISION,
        RT820_SHA256,
        "technical_rt820_code_install_human_decisions.v0.1",
        "IGOR_RT820_CODE_INSTALL_APPROVED_NOT_APPLIED",
        "IGOR-RT820-CODE-INSTALL-2024-086-001",
    ),
)

FINGERPRINT = "4b5cf23236653dfd33e27eefa8034ad2a779b5e2b40f0adc972ee49912dbc0ec"
FINGERPRINT_COMPONENTS = [
    {
        "component_code": "EKF-AD12-1P-N-C16-30MA-4P5KA",
        "component_qty": 1,
        "install_type": "diff_1p_n",
    },
    {
        "component_code": "EKF-RT-820",
        "component_qty": 1,
        "install_type": "temperature_relay_din_2mod",
    },
    {
        "component_code": "EKF-VA47-29-2P",
        "component_qty": 1,
        "install_type": "modular_2p",
    },
]
POSITION_SCOPE = (
    (
        "9",
        "TFE-006",
        5,
        "Секция 9_ЭОМ.pdf",
        "b03d2d87f8ce6a8def89eed3e796dd5daaad1ba9ae55e07c5d643acfaa417e46",
        11,
        27,
    ),
    (
        "11",
        "TFE-029",
        28,
        "Секция 11_ЭОМ.pdf",
        "a00829db7ca196995a53b8313106e90037990a5284cef8fa7dcda92cdc24137e",
        35,
        53,
    ),
    (
        "13",
        "TFE-052",
        51,
        "Секция 13_ЭОМ.pdf",
        "02dde3268d3ceef4d4f0ad6e616f44bbfe37fe8f66a39d4b7fabb4a04b0aa6c2",
        55,
        75,
    ),
    (
        "15",
        "TFE-074",
        73,
        "Секция 15_ЭОМ.pdf",
        "4ca1bd6f27d6474e0fbf2b56d67ba8100016d4350556e704a91fc880ad0a62dd",
        78,
        100,
    ),
)


class ContractError(ValueError):
    """Raised when exact profile-successor requirements are not met."""


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


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
    if not isinstance(value, dict):
        raise ContractError(f"{description} root must be an object")
    return value, raw


def decision_binding(
    role: str,
    path: Path,
    sha256: str,
    schema: str,
    status: str,
    decision_id: str,
) -> dict[str, Any]:
    return {
        "role": role,
        "path": str(path),
        "sha256": sha256,
        "schema_version": schema,
        "status": status,
        "decision_id": decision_id,
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_status": "NOT_APPLIED",
    }


def validate_base_profile(base: Mapping[str, Any]) -> None:
    require(
        base.get("schema_version")
        == "technical_invoice519_pricing_profile_human_decisions.v0.1",
        "base profile schema mismatch",
    )
    require(base.get("project_id") == PROJECT_ID, "base profile project mismatch")
    require(
        base.get("status") == "IGOR_INVOICE519_PRICING_PROFILE_APPROVED_NOT_APPLIED",
        "base profile status mismatch",
    )
    require(base.get("application_status") == "NOT_APPLIED", "base profile applied")
    require(base.get("scope_expansion") is False, "base profile scope expansion")
    require(
        base.get("immutable_state") == {"immutable": True, "no_overwrite": True},
        "base profile immutability mismatch",
    )
    current = base.get("current_completed_technical_scope")
    require(isinstance(current, Mapping), "base current scope missing")
    require(
        current.get("coverage")
        == {
            "technical_cabinet_groups": 14,
            "section_aware_pricing_positions": 51,
            "physical_cabinets": 133,
            "composition_fingerprints": 11,
        },
        "base profile coverage mismatch",
    )
    require(len(current.get("cabinet_groups", [])) == 14, "base group count mismatch")
    require(
        len(current.get("pricing_positions", [])) == 51, "base position count mismatch"
    )
    require(
        len(current.get("composition_fingerprints", [])) == 11,
        "base fingerprint count mismatch",
    )
    safety = base.get("safety_flags")
    require(
        isinstance(safety, Mapping)
        and bool(safety)
        and all(value is False for value in safety.values()),
        "base profile safety flags must all be false",
    )


def validate_decision(
    value: Mapping[str, Any], contract: tuple[str, Path, str, str, str, str]
) -> None:
    role, _path, _sha, schema, status, decision_id = contract
    authority = value.get("authority")
    if isinstance(authority, Mapping):
        authority = authority.get("authority")
    require(value.get("schema_version") == schema, f"{role} schema mismatch")
    require(value.get("status") == status, f"{role} status mismatch")
    require(value.get("decision_id") == decision_id, f"{role} decision mismatch")
    require(authority == "IGOR_DIRECT_HUMAN_APPROVAL", f"{role} authority mismatch")
    require(value.get("application_status") == "NOT_APPLIED", f"{role} applied")
    require(value.get("scope_expansion") is False, f"{role} scope expansion")


def validate_decisions(
    composition: Mapping[str, Any],
    cabinet: Mapping[str, Any],
    rt820: Mapping[str, Any],
) -> None:
    for value, contract in zip(
        (composition, cabinet, rt820), DECISION_CONTRACTS, strict=True
    ):
        validate_decision(value, contract)
    require(
        [item.get("section") for item in composition.get("exact_scope", [])]
        == ["9", "11", "13", "15"],
        "composition section scope mismatch",
    )
    calculation = cabinet.get("calculation_contract")
    require(isinstance(calculation, Mapping), "cabinet calculation missing")
    require(
        calculation.get("inputs_kzt") == {"X": 6936, "I": 0, "G": 20450, "H": 1764}
        and calculation.get("raw_unit_result_kzt") == "53762.72702586206896551724138"
        and calculation.get("approved_calculated_unit_price_kzt") == 53763
        and calculation.get("physical_multiplicity") == 4
        and calculation.get("approved_calculated_exact_scope_total_kzt") == 215052,
        "ШУ-Т1 pricing calculation contract mismatch",
    )
    rt = rt820.get("approved_code_install_contract")
    work = rt820.get("pricing_work_semantics")
    tst = rt820.get("tst05_bundle_semantics")
    require(
        isinstance(rt, Mapping)
        and rt.get("internal_component_code") == "EKF-RT-820"
        and rt.get("install_type") == "temperature_relay_din_2mod"
        and rt.get("module_width_din") == 2,
        "RT-820 technical contract mismatch",
    )
    require(
        isinstance(work, Mapping)
        and work.get("material_price_kzt_per_complete_set") == 15000
        and work.get("work_price_kzt_per_complete_set") == 900
        and work.get("work_price_semantics") == "EXACT_COMPONENT_WORK_PRICE"
        and work.get("generic_modular_2p_work_price_prohibited") is True
        and work.get("family_fallback_prohibited") is True
        and work.get("fuzzy_fallback_prohibited") is True,
        "RT-820 work/fallback contract mismatch",
    )
    require(
        isinstance(tst, Mapping)
        and tst.get("separate_component_row") is False
        and tst.get("separate_material_charge") is False
        and tst.get("separate_work_charge") is False,
        "TST05 double-count guard mismatch",
    )


def validate_completed_successor(value: Mapping[str, Any]) -> None:
    source = value.get("source")
    completion = value.get("completion")
    groups = value.get("cabinet_groups")
    rows = value.get("calculator_input_format", {}).get("row_drafts")
    require(
        value.get("schema_version") == "price_calculator_input_draft.v0.2",
        "technical successor schema mismatch",
    )
    require(isinstance(source, Mapping), "technical successor source missing")
    metadata = source.get("additive_completed_input_successor")
    require(
        isinstance(metadata, Mapping)
        and metadata.get("contract") == TECHNICAL_SUCCESSOR_CONTRACT
        and metadata.get("direct_human_decision_inputs")
        == [decision_binding(*contract) for contract in DECISION_CONTRACTS]
        and metadata.get("scope_expansion") is False,
        "technical successor bindings mismatch",
    )
    require(
        isinstance(groups, list) and len(groups) == 15,
        "technical successor groups mismatch",
    )
    require(
        isinstance(rows, list) and len(rows) == 112, "technical successor rows mismatch"
    )
    require(
        groups[-1].get("cabinet_group_id") == "CABINET-GROUP-015"
        and groups[-1].get("product_name") == "ШУ-Т1"
        and groups[-1].get("row_draft_ids")
        == ["ROW-DRAFT-0110", "ROW-DRAFT-0111", "ROW-DRAFT-0112"],
        "technical successor ШУ-Т1 group mismatch",
    )
    require(
        [row.get("calculator_values") for row in rows[-3:]]
        == [
            {
                "product_name": "ШУ-Т1",
                "cabinet_code": "CAB-KRN-12",
                "consumables_factor": 1.2,
                "component_qty": 1,
                "component_code": "EKF-RT-820",
                "install_type": "temperature_relay_din_2mod",
            },
            {
                "product_name": "ШУ-Т1",
                "cabinet_code": "CAB-KRN-12",
                "consumables_factor": 1.2,
                "component_qty": 1,
                "component_code": "EKF-AD12-1P-N-C16-30MA-4P5KA",
                "install_type": "diff_1p_n",
            },
            {
                "product_name": "ШУ-Т1",
                "cabinet_code": "CAB-KRN-12",
                "consumables_factor": 1.2,
                "component_qty": 1,
                "component_code": "EKF-VA47-29-2P",
                "install_type": "modular_2p",
            },
        ],
        "technical successor ШУ-Т1 row values mismatch",
    )
    require(
        isinstance(completion, Mapping)
        and completion.get("scope", {}).get("component_groups") == 34
        and completion.get("scope", {}).get("rows") == "112/112"
        and completion.get("scope", {}).get("cabinet_groups") == "15/15",
        "technical successor completion scope mismatch",
    )


def fingerprint_from_rows(rows: Sequence[Mapping[str, Any]]) -> str:
    components = sorted(
        (
            {
                "component_code": row["calculator_values"]["component_code"],
                "component_qty": row["calculator_values"]["component_qty"],
                "install_type": row["calculator_values"]["install_type"],
            }
            for row in rows
        ),
        key=lambda item: (
            item["component_code"],
            item["component_qty"],
            item["install_type"],
        ),
    )
    encoded = json.dumps(
        components, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(encoded)


def appended_group() -> dict[str, Any]:
    return {
        "cabinet_group_id": "CABINET-GROUP-015",
        "completed_input_json_path": "$.cabinet_groups[14]",
        "source_cabinet_template": "ЩРН-12",
        "product_name": "ШУ-Т1",
        "cabinet_code": "CAB-KRN-12",
        "cabinet_base_kzt": 6936,
        "approved_additional_cabinet_cost_kzt": 0,
        "formula_family": "CURRENT_MODULAR_CASE_PROFILE",
        "row_draft_ids": ["ROW-DRAFT-0110", "ROW-DRAFT-0111", "ROW-DRAFT-0112"],
    }


def appended_fingerprint() -> dict[str, Any]:
    return {
        "fingerprint_sha256": FINGERPRINT,
        "canonicalization": (
            "SHA256 UTF-8 canonical JSON of sorted "
            "component_code/component_qty/install_type tuples"
        ),
        "components": copy.deepcopy(FINGERPRINT_COMPONENTS),
        "source_position_ids": ["TFE-006", "TFE-029", "TFE-052", "TFE-074"],
        "pricing_position_ids": [
            "PRICE-POSITION-052",
            "PRICE-POSITION-053",
            "PRICE-POSITION-054",
            "PRICE-POSITION-055",
        ],
    }


def appended_positions() -> list[dict[str, Any]]:
    positions: list[dict[str, Any]] = []
    for offset, (
        section,
        source_position,
        source_index,
        document,
        document_sha,
        invoice_position,
        excel_row,
    ) in enumerate(POSITION_SCOPE, start=52):
        positions.append(
            {
                "pricing_position_id": f"PRICE-POSITION-{offset:03d}",
                "technical_scope_status": "CURRENT_COMPLETED_INPUT_SCOPE",
                "section": section,
                "discipline": "ЭОМ",
                "source_document": {
                    "document_id": document,
                    "sha256": document_sha,
                },
                "source_position_id": source_position,
                "source_position_json_path": f"$.positions[{source_index}]",
                "cabinet_group_id": "CABINET-GROUP-015",
                "cabinet_group_json_path": "$.cabinet_groups[14]",
                "product_name": "ШУ-Т1",
                "cabinet_code": "CAB-KRN-12",
                "row_draft_ids": [
                    "ROW-DRAFT-0110",
                    "ROW-DRAFT-0111",
                    "ROW-DRAFT-0112",
                ],
                "row_draft_json_paths": [
                    "$.calculator_input_format.row_drafts[109]",
                    "$.calculator_input_format.row_drafts[110]",
                    "$.calculator_input_format.row_drafts[111]",
                ],
                "composition_fingerprint_sha256": FINGERPRINT,
                "physical_multiplicity": 1,
                "unit_pricing_before_multiplicity": True,
                "invoice_comparator": {
                    "worksheet": "Лист1",
                    "invoice_position_number": invoice_position,
                    "invoice_product_label": "ШУ-Т1",
                    "quantity_cell": f"E{excel_row}",
                    "unit_price_cell": f"H{excel_row}",
                    "unit_price_kzt": 51313,
                    "manual_override_used": False,
                },
                "pricing_calculation_status": "NOT_EXECUTED",
                "approved_unit_price_kzt": 53763,
                "approved_unit_price_decision_status": "APPROVED_NOT_APPLIED",
            }
        )
    return positions


def build_successor_payload(
    base: Mapping[str, Any],
    completed_successor: Mapping[str, Any],
    completed_successor_path: Path,
    completed_successor_sha256: str,
    composition: Mapping[str, Any],
    cabinet: Mapping[str, Any],
    rt820: Mapping[str, Any],
) -> dict[str, Any]:
    validate_base_profile(base)
    validate_completed_successor(completed_successor)
    validate_decisions(composition, cabinet, rt820)
    require(
        len(completed_successor_sha256) == 64, "technical successor SHA must be exact"
    )
    require(
        fingerprint_from_rows(
            completed_successor["calculator_input_format"]["row_drafts"][-3:]
        )
        == FINGERPRINT,
        "ШУ-Т1 composition fingerprint mismatch",
    )

    successor = copy.deepcopy(dict(base))
    successor["additive_successor"] = {
        "contract": SUCCESSOR_CONTRACT,
        "project_id": PROJECT_ID,
        "parent": {"path": str(BASE_PROFILE), "sha256": BASE_PROFILE_SHA256},
        "completed_input_successor": {
            "path": str(completed_successor_path),
            "sha256": completed_successor_sha256,
            "contract": TECHNICAL_SUCCESSOR_CONTRACT,
        },
        "direct_human_decision_inputs": [
            decision_binding(*contract) for contract in DECISION_CONTRACTS
        ],
        "append_only": True,
        "scope_expansion": False,
        "pricing_calculation_executed": False,
        "approved_shu_t1_unit_price_kzt": 53763,
        "approved_shu_t1_exact_scope_total_kzt": 215052,
        "candidate_project_total_kzt": 11841516,
        "candidate_project_total_status": "DRAFT_PRELIMINARY_PRICE_CALCULATION",
        "price_approval_status": "REQUIRES_IGOR_PRICE_APPROVAL",
    }
    successor["authoritative_inputs"].extend(
        [
            {
                "role": "completed_technical_input_additive_successor",
                "path": str(completed_successor_path),
                "sha256": completed_successor_sha256,
                "schema_or_type": "price_calculator_input_draft.v0.2",
                "purpose": "exact 15-group/112-row additive technical authority",
            },
            *[decision_binding(*contract) for contract in DECISION_CONTRACTS],
        ]
    )
    successor["scope_partition"]["current_completed_technical_scope"]["coverage"] = {
        "technical_cabinet_groups": 15,
        "section_aware_pricing_positions": 55,
        "physical_cabinets": 137,
        "composition_fingerprints": 12,
    }
    current = successor["current_completed_technical_scope"]
    current["coverage"] = {
        "technical_cabinet_groups": 15,
        "section_aware_pricing_positions": 55,
        "physical_cabinets": 137,
        "composition_fingerprints": 12,
    }
    current["products"].append("ШУ-Т1")
    current["modular_formula_family"]["scope_cabinet_group_ids"].append(
        "CABINET-GROUP-015"
    )
    current["cabinet_groups"].append(appended_group())
    current["composition_fingerprints"].append(appended_fingerprint())
    current["pricing_positions"].extend(appended_positions())
    current["shu_t1_approved_calculated_price"] = {
        "sections": ["9", "11", "13", "15"],
        "X_cabinet_base_kzt": 6936,
        "I_additional_cabinet_cost_kzt": 0,
        "G_material_kzt": 20450,
        "H_work_kzt": 1764,
        "raw_unit_price_kzt": "53762.72702586206896551724138",
        "approved_unit_price_kzt": 53763,
        "physical_multiplicity": 4,
        "approved_exact_scope_total_kzt": 215052,
        "round_unit_before_multiplicity": True,
        "decision_status": "APPROVED_NOT_APPLIED",
    }
    successor["validation_summary"]["current_coverage"] = "55/137/12"
    successor["validation_summary"]["additive_successor_contract_validation"] = "PASS"
    validate_successor_payload(
        successor, base, completed_successor_path, completed_successor_sha256
    )
    return successor


def validate_successor_payload(
    successor: Mapping[str, Any],
    base: Mapping[str, Any],
    completed_successor_path: Path,
    completed_successor_sha256: str,
) -> None:
    validate_base_profile(base)
    metadata = successor.get("additive_successor")
    require(isinstance(metadata, Mapping), "profile successor metadata missing")
    require(
        metadata.get("contract") == SUCCESSOR_CONTRACT
        and metadata.get("parent")
        == {"path": str(BASE_PROFILE), "sha256": BASE_PROFILE_SHA256}
        and metadata.get("completed_input_successor")
        == {
            "path": str(completed_successor_path),
            "sha256": completed_successor_sha256,
            "contract": TECHNICAL_SUCCESSOR_CONTRACT,
        }
        and metadata.get("direct_human_decision_inputs")
        == [decision_binding(*contract) for contract in DECISION_CONTRACTS]
        and metadata.get("candidate_project_total_kzt") == 11841516
        and metadata.get("candidate_project_total_status")
        == "DRAFT_PRELIMINARY_PRICE_CALCULATION"
        and metadata.get("price_approval_status") == "REQUIRES_IGOR_PRICE_APPROVAL"
        and metadata.get("scope_expansion") is False,
        "profile successor binding/total contract mismatch",
    )
    current = successor.get("current_completed_technical_scope")
    base_current = base["current_completed_technical_scope"]
    require(isinstance(current, Mapping), "profile successor current scope missing")
    require(
        current.get("coverage")
        == {
            "technical_cabinet_groups": 15,
            "section_aware_pricing_positions": 55,
            "physical_cabinets": 137,
            "composition_fingerprints": 12,
        },
        "profile successor coverage mismatch",
    )
    require(
        current.get("cabinet_groups", [])[:14] == base_current["cabinet_groups"],
        "base profile cabinet-group prefix changed",
    )
    require(
        current.get("composition_fingerprints", [])[:11]
        == base_current["composition_fingerprints"],
        "base profile fingerprint prefix changed",
    )
    require(
        current.get("pricing_positions", [])[:51] == base_current["pricing_positions"],
        "base profile pricing-position prefix changed",
    )
    require(
        current.get("cabinet_groups", [None])[-1] == appended_group(),
        "appended profile group mismatch",
    )
    require(
        current.get("composition_fingerprints", [None])[-1] == appended_fingerprint(),
        "appended profile fingerprint mismatch",
    )
    require(
        current.get("pricing_positions", [])[51:] == appended_positions(),
        "appended profile positions mismatch",
    )
    require(
        len({item["pricing_position_id"] for item in current["pricing_positions"]})
        == 55,
        "pricing-position ID collision",
    )
    require(
        sum(item["physical_multiplicity"] for item in current["pricing_positions"])
        == 137,
        "physical multiplicity coverage mismatch",
    )
    require(
        current.get("products") == [*base_current["products"], "ШУ-Т1"],
        "profile product list is not append-only",
    )
    require(
        all(value is False for value in successor.get("safety_flags", {}).values()),
        "profile successor safety flag became true",
    )
    require(
        successor.get("application_status") == "NOT_APPLIED",
        "profile successor applied",
    )


def serialize(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def ensure_external_output(output: Path) -> None:
    try:
        output.resolve(strict=False).relative_to(REPO_ROOT)
    except ValueError:
        return
    raise ContractError("profile successor output must be outside the repository")


def publish_successor(
    completed_successor_path: Path,
    completed_successor_sha256: str,
    output: Path,
) -> str:
    ensure_external_output(output)
    require(output.parent.is_dir(), "target directory must already exist")
    require(not output.exists(), "output already exists; overwrite is forbidden")
    require(
        len(completed_successor_sha256) == 64
        and completed_successor_sha256 == completed_successor_sha256.lower(),
        "completed successor SHA must be 64 lowercase hexadecimal characters",
    )

    specs = (
        (BASE_PROFILE, BASE_PROFILE_SHA256, "base pricing profile"),
        (
            completed_successor_path,
            completed_successor_sha256,
            "completed-input additive successor",
        ),
        *(
            (path, sha, role)
            for role, path, sha, _schema, _status, _decision_id in DECISION_CONTRACTS
        ),
    )
    loaded: list[tuple[dict[str, Any], bytes]] = []
    for path, expected_sha, description in specs:
        value, raw = load_json(path, description)
        require(
            sha256_bytes(raw) == expected_sha, f"initial SHA mismatch: {description}"
        )
        loaded.append((value, raw))
    base, completed, composition, cabinet, rt820 = (item[0] for item in loaded)
    payload = build_successor_payload(
        base,
        completed,
        completed_successor_path,
        completed_successor_sha256,
        composition,
        cabinet,
        rt820,
    )
    encoded = serialize(payload)
    descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".staging", dir=output.parent
    )
    staging = Path(staging_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        for (path, expected_sha, description), (_value, initial_raw) in zip(
            specs, loaded, strict=True
        ):
            current = path.read_bytes()
            require(current == initial_raw, f"TOCTOU bytes changed: {description}")
            require(
                sha256_bytes(current) == expected_sha,
                f"TOCTOU SHA mismatch: {description}",
            )
        require(not output.exists(), "output appeared before publication")
        os.link(staging, output)
        published, published_raw = load_json(output, "published profile successor")
        require(published_raw == encoded, "published profile bytes mismatch")
        validate_successor_payload(
            published, base, completed_successor_path, completed_successor_sha256
        )
        return sha256_bytes(published_raw)
    finally:
        try:
            staging.unlink()
        except FileNotFoundError:
            pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--completed-input-successor", type=Path, required=True)
    parser.add_argument("--completed-input-successor-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorization", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.authorization != PUBLICATION_AUTHORIZATION:
        raise ContractError(
            "exact pricing-profile-successor publication acknowledgement is required"
        )
    digest = publish_successor(
        args.completed_input_successor,
        args.completed_input_successor_sha256,
        args.output,
    )
    print(f"PUBLISHED_IMMUTABLE_NO_OVERWRITE {args.output} SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
