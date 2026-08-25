"""Run the read-only price calculator from a validated completed draft."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = Path(__file__).with_name(
    "validate_completed_price_calculator_input_draft.py"
)
CALCULATOR_PATH = Path(__file__).with_name("calc_quote_price_draft.py")
CUSTOM_SCHE_RESOLVER_PATH = Path(__file__).with_name(
    "resolve_custom_sche_cabinet_base_cost.py"
)

REPORT_START = "CHECKED_PRICE_CALCULATOR_RUN_REPORT_START"
REPORT_END = "CHECKED_PRICE_CALCULATOR_RUN_REPORT_END"
MODE = "checked read-only price calculator run from completed draft"
COMMERCIAL_STATUS = (
    "draft price calculation only; not price approval; not commercial CSV; "
    "not client-ready КП"
)
HUMAN_APPROVAL = (
    "Igor approval required before commercial CSV, КП sending or production"
)
CSV_DELIMITER = ";"
CALCULATOR_COLUMNS = (
    "product_name",
    "cabinet_code",
    "consumables_factor",
    "component_code",
    "component_qty",
    "install_type",
)
TECHNICAL_CALCULATOR_COLUMNS = CALCULATOR_COLUMNS + (
    "component_label",
    "cabinet_label",
)
SHU_T2_RT820_BINDING_COLUMNS = (
    "technical_successor_contract",
    "technical_successor_sha256",
    "pricing_profile_contract",
    "pricing_profile_sha256",
    "human_decision_sha256",
)
SHU_T2_TECHNICAL_CALCULATOR_COLUMNS = (
    TECHNICAL_CALCULATOR_COLUMNS + SHU_T2_RT820_BINDING_COLUMNS
)
V02_SCHEMA_VERSION = "price_calculator_input_draft.v0.2"
CUSTOM_SCHE_CABINET_CODE = "CAB-SCHE-BI-900X900X120-M12"
CUSTOM_SCHE_PRODUCT_NAMES = ("ЩЭ-3кв", "ЩЭ-4кв", "ЩЭ-5кв", "ЩЭ-6кв")
CUSTOM_SCHE_CABINET_LABEL = "Встроенный ЩЭ, 900×900×120 мм, металл 1.2 мм"
PRICING_PROFILE_PATH = (
    Path(
        r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-"
        "INVOICE519-PRICING-PROFILE-DECISION-20260814-001"
    )
    / "technical-invoice519-pricing-profile-human-decisions-v0.1.json"
)
PRICING_PROFILE_SHA256 = (
    "60d1f9c794b7d1164feaa20dbfaba6493dac8da480462941c3a6b7e17871c2a8"
)
PRICING_PROFILE_SCHEMA = "technical_invoice519_pricing_profile_human_decisions.v0.1"
PRICING_PROFILE_STATUS = "IGOR_INVOICE519_PRICING_PROFILE_APPROVED_NOT_APPLIED"
PRICING_PROFILE_DECISION_ID = "IGOR-INVOICE519-PRICING-PROFILE-2024-086-001"
PRICING_PROFILE_PROJECT_ID = "2024/086"
PROFILE_DRAFT_STATUS = "DRAFT_PRELIMINARY_PRICE_CALCULATION"
PROFILE_APPROVAL_STATUS = "REQUIRES_IGOR_PRICE_APPROVAL"
EXPECTED_PROFILE_COVERAGE = {
    "technical_cabinet_groups": 14,
    "section_aware_pricing_positions": 51,
    "physical_cabinets": 133,
    "composition_fingerprints": 11,
}
EXPECTED_PROFILE_PRODUCTS = [
    "ПР",
    "Щоф",
    "ШУ-Т2",
    "ЩАО-1Ж",
    "ЩАО-2Ж",
    "ЩАО-3Ж",
    "ЩО-1Ж",
    "ЩО-2Ж",
    "ЩС",
    "ЩЭ-3кв",
    "ЩЭ-4кв",
    "ЩЭ-5кв",
    "ЩЭ-6кв",
    "ЩО-3Ж",
]
ADDITIVE_PROFILE_CONTRACT = (
    "controlled_additive_invoice519_pricing_profile_successor.v0.1"
)
ADDITIVE_COMPLETED_CONTRACT = "controlled_additive_completed_input_successor.v0.1"
ADDITIVE_PROFILE_COVERAGE = {
    "technical_cabinet_groups": 15,
    "section_aware_pricing_positions": 55,
    "physical_cabinets": 137,
    "composition_fingerprints": 12,
}
ADDITIVE_PROFILE_PRODUCTS = [*EXPECTED_PROFILE_PRODUCTS, "ШУ-Т1"]
SHU_T1_FINGERPRINT = "4b5cf23236653dfd33e27eefa8034ad2a779b5e2b40f0adc972ee49912dbc0ec"
SHU_T2_RT820_PROFILE_CONTRACT = "controlled_shu_t2_rt820_pricing_profile_successor.v0.1"
SHU_T2_RT820_TECHNICAL_CONTRACT = "controlled_shu_t2_rt820_technical_successor.v0.1"
SHU_T2_RT820_PROFILE_SHA256 = (
    "7b66d2431e2a323f9c0cd60bdaeff2d5d26ebfc0b430f2f6a5530e3a064dc701"
)
SHU_T2_RT820_PROFILE_COVERAGE = {
    "technical_cabinet_groups": 15,
    "section_aware_pricing_positions": 55,
    "physical_cabinets": 137,
    "composition_fingerprints": 11,
}
SHU_T2_RT820_PARENT_PROFILE_PATH = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-"
    "SHU-T1-PRICING-PROFILE-SUCCESSOR-20260820-001\\"
    "invoice519-pricing-profile-additive-successor.json"
)
SHU_T2_RT820_PARENT_PROFILE_SHA256 = (
    "10d4301923b1ae141ae228c319f38e7281810e40c6990f0b2d533e9e20763424"
)
SHU_T2_RT820_TECHNICAL_PATH = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-"
    "SHU-T2-RT820-TECHNICAL-SUCCESSOR-20260824-001\\"
    "price-calculator-input-v0.2-completed-shu-t2-rt820-successor.json"
)
SHU_T2_RT820_TECHNICAL_SHA256 = (
    "c27c2c3032699cb07c981aeb4af429b27ec18180225319f45ce65ab77fedee44"
)
SHU_T2_RT820_DECISION_PATH = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-"
    "SHU-T2-RT820-SCOPE-DECISION-20260820-001\\"
    "technical-shu-t2-rt820-scope-human-decision-v0.1.json"
)
SHU_T2_RT820_DECISION_SHA256 = (
    "92a79401591fa6202af493848dd979a227ae20da8e66b8dea6e8084fc80c2ac6"
)
SHU_T2_RT820_DECISION_ID = "IGOR-SHU-T2-RT820-SCOPE-2024-086-001"
ADDITIVE_DECISION_BINDINGS = [
    {
        "role": "technical_composition_human_decision",
        "path": (
            "C:\\Users\\IgorN\\Documents\\production_ai_cases\\"
            "CASE-QF-PROJECT-2024-086-SHU-T1-HUMAN-DECISIONS-20260817-001\\"
            "technical-shu-t1-composition-human-decisions-v0.1.json"
        ),
        "sha256": "bccf62150488037b7df50804c88454119748be103da22dad456db2969126c008",
        "schema_version": "technical_shu_t1_composition_human_decisions.v0.1",
        "status": "IGOR_SHU_T1_COMPOSITION_APPROVED_NOT_APPLIED",
        "decision_id": "IGOR-SHU-T1-COMPOSITION-2024-086-001",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_status": "NOT_APPLIED",
    },
    {
        "role": "cabinet_pricing_human_decision",
        "path": (
            "C:\\Users\\IgorN\\Documents\\production_ai_cases\\"
            "CASE-QF-PROJECT-2024-086-SHU-T1-CABINET-PRICING-DECISION-20260817-001\\"
            "technical-shu-t1-cabinet-pricing-human-decisions-v0.1.json"
        ),
        "sha256": "b3a1bb84bacb2cc5127752cb378b2151552fcb443f02116b12269a086add4247",
        "schema_version": "technical_shu_t1_cabinet_pricing_human_decisions.v0.1",
        "status": "APPROVED_NOT_APPLIED",
        "decision_id": "IGOR-SHU-T1-CABINET-PRICING-2024-086-001",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_status": "NOT_APPLIED",
    },
    {
        "role": "rt820_code_install_human_decision",
        "path": (
            "C:\\Users\\IgorN\\Documents\\production_ai_cases\\"
            "CASE-QF-PROJECT-2024-086-RT820-CODE-INSTALL-DECISION-20260818-001\\"
            "technical-rt820-code-install-human-decisions-v0.1.json"
        ),
        "sha256": "95c9f2610a6e8429242789e17c3b69ffae31db28655736aed12caa1d3939630f",
        "schema_version": "technical_rt820_code_install_human_decisions.v0.1",
        "status": "IGOR_RT820_CODE_INSTALL_APPROVED_NOT_APPLIED",
        "decision_id": "IGOR-RT820-CODE-INSTALL-2024-086-001",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_status": "NOT_APPLIED",
    },
]
EXPECTED_PROFILE_INPUTS = (
    (
        "completed_technical_input",
        r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-PRICE-CALCULATOR-APPLICATION-20260812-001\price-calculator-input-v0.2-completed.json",
        "71d933c14a603c24ba8072311b84992d1708cbc7ff1fede59727e727218f5bdb",
        "price_calculator_input_draft.v0.2",
    ),
    (
        "main_price_workbook",
        str(
            Path(r"C:\Users\IgorN\Documents\invoice_quote_filler_data\prices\current")
            / "Таблица 05.01.2026 верная.xlsx"
        ),
        "f8bd69da1f61612d3853e608333486dcd3b6ecd572cd98beb2247c6accb31b5f",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    (
        "pr_sections_9_13_calculation_workbook",
        r"C:\Users\IgorN\Downloads\Таблица 05.01.2026 верная-ПР-9-13.xlsx",
        "430d3c2dfc770b4a447fc015b8fc00788dfeb14e4312926953d224a60d097add",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    (
        "custom_sche_metal_workbook",
        str(
            Path(r"C:\Users\IgorN\Documents\invoice_quote_filler_data\prices\current")
            / "прайс_металл_лотки_крышки с 2026.06.18.xlsx"
        ),
        "b51d7087e0bd8f92e48985294062ead6826c6b50ce3cfacd0f9d0dc22c05f7f2",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    (
        "canonical_invoice_519",
        r"C:\Users\IgorN\Downloads\2026.06.22_519_ТОО «Sensata Industrial».xlsx",
        "17e31d0312f728800d31fd4f125d285edb1114880500d4833261239b87ab58b5",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    (
        "applied_component_lineage",
        r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-HUMAN-DECISIONS-20260731-023\component-replay-applied-bundle-v0.23.json",
        "6433e862c7281ac699a12b81e30a02e7f45702ddab22441efd2c79d36589dd6f",
        "component_replay_applied_bundle.v0.23",
    ),
    (
        "canonical_position_lineage",
        r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-REPLAY-V021-20260729-001\canonical-component-replay-readiness-bundle-v021\component_replay_readiness_bundle.json",
        "41ca4e3b63433c8f06c7630565c3d5d5380659e49027bf091a6aff6ab007123e",
        "component_replay_readiness_bundle.v0.2",
    ),
)
EXPECTED_SCHE_APARTMENTS = {"ЩЭ-3кв": 3, "ЩЭ-4кв": 4, "ЩЭ-5кв": 5, "ЩЭ-6кв": 6}
EXPECTED_RESERVED_FAMILIES = (
    "ВРУ250А",
    "ВРУ400А",
    "ВРУ630А",
    "ВРУ-расп.",
    "АВР Г-Г",
    "АВР Г-Д",
    "АВР-Г-Г-Д",
    "ШРС",
    "ВРУ-ВА",
)
CALCULATOR_SUMMARY_KEYS = (
    "Status",
    "Mode",
    "Input rows count",
    "Cabinet",
    "Cabinet price",
    "Component material total",
    "Work total",
    "Additional materials total",
    "Consumables factor",
    "Base",
    "Total preliminary price",
    "Red flags",
    "Commercial status",
    "Human Approval",
)


@dataclass
class CalculatorProcessResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ItemCalculatorInput:
    product_name: str
    cabinet_code: str
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class ItemCalculationSummary:
    product_name: str
    input_rows_count: int
    cabinet: str
    cabinet_price: str
    component_material_total: str
    work_total: str
    additional_materials_total: str
    total_preliminary_price: int


@dataclass(frozen=True)
class ProfilePositionInput:
    pricing_position_id: str
    section: str
    discipline: str
    source_document: Mapping[str, Any]
    cabinet_group_id: str
    product_name: str
    cabinet_code: str
    formula_family: str
    row_draft_ids: list[str]
    rows: list[dict[str, Any]]
    composition_fingerprint_sha256: str
    physical_multiplicity: int
    apartment_count: int | None
    approved_unit_price_kzt: int | None
    cabinet_base_kzt: int
    additional_cabinet_cost_kzt: int


@dataclass(frozen=True)
class ProfilePositionCalculation:
    pricing_position_id: str
    section: str
    discipline: str
    source_document: Mapping[str, Any]
    cabinet_group_id: str
    product_name: str
    row_draft_ids: list[str]
    composition_fingerprint_sha256: str
    formula_family: str
    cabinet_base_kzt: int
    additional_cabinet_cost_kzt: int
    component_material_total_kzt: int
    work_total_kzt: int
    apartment_component_kzt: int
    apartment_count: int | None
    unrounded_unit_price_kzt: str
    rounding_stage: str
    rounding_mode: str
    rounded_unit_price_kzt: int
    physical_multiplicity: int
    position_total_kzt: int


@dataclass
class CheckedRunResult:
    completed_input_json: Path
    price_workbook: Path
    status: str = "FAIL"
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "completed input validation": "fail",
            "CSV bridge": "fail",
            "custom ЩЭ resolver": "pass",
            "calculator execution": "fail",
            "temp cleanup": "pass",
            "safety boundary": "fail",
        }
    )
    red_flags: list[str] = field(default_factory=list)
    calculator_returncode: int | None = None
    calculator_stdout: str = ""
    calculator_stderr: str = ""
    temp_csv_path: Path | None = None
    temp_csv_deleted: bool = True
    temp_csv_paths: list[Path] = field(default_factory=list)
    calculator_runs: list[CalculatorProcessResult] = field(default_factory=list)
    item_summaries: list[ItemCalculationSummary] = field(default_factory=list)
    overall_preliminary_total: int | None = None
    pricing_status: str | None = None
    approval_status: str | None = None
    pricing_profile_provenance: dict[str, str] = field(default_factory=dict)
    input_sha_provenance: dict[str, str] = field(default_factory=dict)
    position_calculations: list[ProfilePositionCalculation] = field(
        default_factory=list
    )
    group_summaries: dict[str, int] = field(default_factory=dict)
    preliminary_project_total: int | None = None
    non_approval_flags: dict[str, bool] = field(default_factory=dict)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a completed price-calculator input draft, bridge it to "
            "the existing CSV contract, and run the read-only calculator."
        )
    )
    parser.add_argument("--completed-input-json", required=True, type=Path)
    parser.add_argument("--price-workbook", required=True, type=Path)
    parser.add_argument("--custom-sche-metal-workbook", type=Path)
    parser.add_argument("--pricing-profile", required=True, type=Path)
    parser.add_argument(
        "--expected-pricing-profile-sha256",
        required=True,
    )
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def add_red_flag(result: CheckedRunResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_completed_price_calculator_input_draft_for_checked_runner",
        VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("completed input validator could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_completed_input_validation(result: CheckedRunResult) -> bool:
    validator = load_validator_module()
    validation = validator.validate_completed_price_calculator_input_draft(
        result.completed_input_json
    )

    if validation.status == "PASS":
        result.checks["completed input validation"] = "pass"
        if validation.checks.get("safety boundary") == "pass":
            result.checks["safety boundary"] = "pass"
        return True

    add_red_flag(result, "completed input validation failed")
    for red_flag in validation.red_flags:
        add_red_flag(result, f"completed input: {red_flag}")
    if validation.checks.get("safety boundary") == "pass":
        result.checks["safety boundary"] = "pass"
    return False


def load_completed_input_json(result: CheckedRunResult) -> Mapping[str, Any] | None:
    try:
        data = json.loads(result.completed_input_json.read_text(encoding="utf-8"))
    except FileNotFoundError:
        add_red_flag(result, "completed input JSON does not exist")
        return None
    except UnicodeDecodeError:
        add_red_flag(result, "completed input JSON must be valid UTF-8")
        return None
    except json.JSONDecodeError:
        add_red_flag(result, "completed input JSON is malformed")
        return None
    except OSError:
        add_red_flag(result, "completed input JSON could not be read")
        return None

    if not isinstance(data, Mapping):
        add_red_flag(result, "completed input JSON root must be an object")
        return None
    return cast(Mapping[str, Any], data)


class DuplicateJsonKeyError(ValueError):
    """Raised when a trusted JSON object repeats a key."""


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(key)
        result[key] = value
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pricing_profile(
    result: CheckedRunResult,
    pricing_profile_path: Path,
    expected_sha256: str,
) -> Mapping[str, Any] | None:
    path = resolved(pricing_profile_path)
    try:
        payload = path.read_bytes()
    except OSError:
        add_red_flag(result, "pricing profile could not be read")
        return None
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != expected_sha256:
        add_red_flag(result, "pricing profile SHA-256 mismatch")
        return None
    try:
        data = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except UnicodeDecodeError:
        add_red_flag(result, "pricing profile must be valid UTF-8")
        return None
    except DuplicateJsonKeyError as exc:
        add_red_flag(result, f"pricing profile contains duplicate key: {exc}")
        return None
    except json.JSONDecodeError:
        add_red_flag(result, "pricing profile JSON is malformed")
        return None
    if not isinstance(data, Mapping):
        add_red_flag(result, "pricing profile root must be an object")
        return None
    additive = isinstance(data.get("additive_successor"), Mapping) or isinstance(
        data.get("shu_t2_rt820_pricing_profile_successor"), Mapping
    )
    if not additive and (
        path != resolved(PRICING_PROFILE_PATH)
        or expected_sha256 != PRICING_PROFILE_SHA256
    ):
        add_red_flag(result, "pricing profile path/SHA is not the canonical exact base")
        return None
    if (
        isinstance(data.get("shu_t2_rt820_pricing_profile_successor"), Mapping)
        and expected_sha256 != SHU_T2_RT820_PROFILE_SHA256
    ):
        add_red_flag(result, "SHU-T2 pricing profile exact frozen SHA-256 mismatch")
        return None
    return cast(Mapping[str, Any], data)


def profile_check(
    result: CheckedRunResult,
    condition: bool,
    message: str,
) -> bool:
    if condition:
        return True
    add_red_flag(result, f"pricing profile: {message}")
    return False


def additive_profile_metadata(
    profile: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    metadata = profile.get("additive_successor")
    return cast(Mapping[str, Any], metadata) if isinstance(metadata, Mapping) else None


def shu_t2_profile_metadata(
    profile: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    metadata = profile.get("shu_t2_rt820_pricing_profile_successor")
    return cast(Mapping[str, Any], metadata) if isinstance(metadata, Mapping) else None


def has_additive_scope(profile: Mapping[str, Any]) -> bool:
    return (
        additive_profile_metadata(profile) is not None
        or shu_t2_profile_metadata(profile) is not None
    )


def validate_shu_t2_profile_envelope(
    profile: Mapping[str, Any], result: CheckedRunResult
) -> bool:
    metadata = shu_t2_profile_metadata(profile)
    if metadata is None:
        return True
    parent = metadata.get("parent_pricing_profile")
    technical = metadata.get("technical_successor")
    decision = metadata.get("human_decision")
    workbook = metadata.get("pricing_workbook")
    invariants = metadata.get("preliminary_not_approved_invariants")
    valid = all(
        (
            metadata.get("contract") == SHU_T2_RT820_PROFILE_CONTRACT,
            metadata.get("project_id") == PRICING_PROFILE_PROJECT_ID,
            parent
            == {
                "path": str(resolved(SHU_T2_RT820_PARENT_PROFILE_PATH)),
                "sha256": SHU_T2_RT820_PARENT_PROFILE_SHA256,
                "schema_or_type": PRICING_PROFILE_SCHEMA,
            },
            isinstance(technical, Mapping),
            isinstance(technical, Mapping)
            and technical.get("path") == str(resolved(SHU_T2_RT820_TECHNICAL_PATH)),
            isinstance(technical, Mapping)
            and technical.get("sha256") == SHU_T2_RT820_TECHNICAL_SHA256,
            isinstance(technical, Mapping)
            and technical.get("contract") == SHU_T2_RT820_TECHNICAL_CONTRACT,
            isinstance(decision, Mapping),
            isinstance(decision, Mapping)
            and decision.get("path") == str(resolved(SHU_T2_RT820_DECISION_PATH)),
            isinstance(decision, Mapping)
            and decision.get("sha256") == SHU_T2_RT820_DECISION_SHA256,
            isinstance(decision, Mapping)
            and decision.get("decision_id") == SHU_T2_RT820_DECISION_ID,
            isinstance(decision, Mapping)
            and decision.get("authority") == "IGOR_DIRECT_HUMAN_APPROVAL",
            isinstance(decision, Mapping)
            and decision.get("application_status") == "NOT_APPLIED",
            isinstance(workbook, Mapping),
            isinstance(workbook, Mapping)
            and workbook.get("path")
            == str(resolved(Path(EXPECTED_PROFILE_INPUTS[1][1]))),
            isinstance(workbook, Mapping)
            and workbook.get("sha256") == EXPECTED_PROFILE_INPUTS[1][2],
            isinstance(workbook, Mapping)
            and workbook.get("source_range") == "КРН!A19:C19",
            isinstance(workbook, Mapping) and workbook.get("material_kzt") == 15000,
            isinstance(workbook, Mapping) and workbook.get("work_kzt") == 900,
            metadata.get("controlled_replacement") is True,
            metadata.get("append_only") is False,
            metadata.get("scope_expansion") is False,
            metadata.get("coverage_transition")
            == {
                "cabinet_groups": "15->15",
                "pricing_positions": "55->55",
                "physical_cabinets": "137->137",
                "technical_rows": "112->116",
                "composition_fingerprints": "12->11",
            },
            metadata.get("old_fingerprint_removed")
            == "99db78a5c3c7688a9e2cebbbe57f41489af797bbc61f2b1fa38492a42329cb79",
            metadata.get("merged_fingerprint") == SHU_T1_FINGERPRINT,
            metadata.get("tst05_provenance_only") is True,
            metadata.get("generic_work_432_prohibited") is True,
            metadata.get("fallback_prohibited") is True,
            metadata.get("pricing_calculation_executed") is False,
            metadata.get("approved_unit_price_kzt") is None,
            metadata.get("application_status") == "NOT_APPLIED",
            metadata.get("price_approval_status") == PROFILE_APPROVAL_STATUS,
            isinstance(invariants, Mapping),
            isinstance(invariants, Mapping)
            and invariants.get("status") == "NOT_CALCULATED_NOT_APPROVED",
            isinstance(invariants, Mapping)
            and invariants.get("unit_candidate_kzt") == 53763,
            isinstance(invariants, Mapping)
            and invariants.get("four_position_candidate_kzt") == 215052,
            isinstance(invariants, Mapping)
            and invariants.get("delta_from_prior_checked_candidate_kzt") == 122276,
            isinstance(invariants, Mapping)
            and invariants.get("preliminary_project_candidate_kzt") == 11963792,
            isinstance(invariants, Mapping) and invariants.get("approved") is False,
            isinstance(invariants, Mapping) and invariants.get("applied") is False,
        )
    )
    return profile_check(result, valid, "SHU-T2 RT-820 successor envelope mismatch")


def validate_additive_profile_envelope(
    profile: Mapping[str, Any], result: CheckedRunResult
) -> bool:
    metadata = additive_profile_metadata(profile)
    if metadata is None:
        return True
    completed = metadata.get("completed_input_successor")
    valid = all(
        (
            metadata.get("contract") == ADDITIVE_PROFILE_CONTRACT,
            metadata.get("project_id") == PRICING_PROFILE_PROJECT_ID,
            metadata.get("parent")
            == {"path": str(PRICING_PROFILE_PATH), "sha256": PRICING_PROFILE_SHA256},
            isinstance(completed, Mapping),
            isinstance(completed, Mapping)
            and completed.get("contract") == ADDITIVE_COMPLETED_CONTRACT,
            isinstance(completed, Mapping) and isinstance(completed.get("path"), str),
            isinstance(completed, Mapping)
            and isinstance(completed.get("sha256"), str)
            and len(completed["sha256"]) == 64,
            metadata.get("direct_human_decision_inputs") == ADDITIVE_DECISION_BINDINGS,
            metadata.get("append_only") is True,
            metadata.get("scope_expansion") is False,
            metadata.get("pricing_calculation_executed") is False,
            metadata.get("approved_shu_t1_unit_price_kzt") == 53763,
            metadata.get("approved_shu_t1_exact_scope_total_kzt") == 215052,
            metadata.get("candidate_project_total_kzt") == 11841516,
            metadata.get("candidate_project_total_status") == PROFILE_DRAFT_STATUS,
            metadata.get("price_approval_status") == PROFILE_APPROVAL_STATUS,
        )
    )
    return profile_check(result, valid, "additive successor envelope mismatch")


def validate_pricing_profile_contract(
    profile: Mapping[str, Any],
    result: CheckedRunResult,
) -> bool:
    authority = profile.get("authority")
    immutable = profile.get("immutable_state")
    checks = [
        profile_check(
            result,
            profile.get("schema_version") == PRICING_PROFILE_SCHEMA,
            "schema mismatch",
        ),
        profile_check(
            result,
            profile.get("project_id") == PRICING_PROFILE_PROJECT_ID,
            "project mismatch",
        ),
        profile_check(
            result,
            profile.get("status") == PRICING_PROFILE_STATUS,
            "status mismatch",
        ),
        profile_check(
            result,
            profile.get("decision_id") == PRICING_PROFILE_DECISION_ID,
            "decision ID mismatch",
        ),
        profile_check(
            result,
            authority
            == {
                "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
                "decision_source": "DIRECT_IGOR_INSTRUCTION_2026-08-14",
                "no_scope_expansion": True,
            },
            "authority mismatch",
        ),
        profile_check(
            result,
            immutable == {"immutable": True, "no_overwrite": True},
            "immutable/no-overwrite mismatch",
        ),
        profile_check(
            result,
            profile.get("application_status") == "NOT_APPLIED",
            "application status mismatch",
        ),
        profile_check(
            result,
            profile.get("scope_expansion") is False,
            "scope expansion is forbidden",
        ),
    ]
    additive = has_additive_scope(profile)
    shu_t2 = shu_t2_profile_metadata(profile) is not None
    actual_inputs = profile.get("authoritative_inputs")
    input_projection: tuple[tuple[Any, Any, Any, Any], ...] = ()
    if isinstance(actual_inputs, list):
        input_projection = tuple(
            (
                item.get("role"),
                item.get("path"),
                item.get("sha256"),
                item.get("schema_or_type"),
            )
            for item in actual_inputs
            if isinstance(item, Mapping)
        )
    inputs_valid = input_projection == EXPECTED_PROFILE_INPUTS
    if additive and not shu_t2 and isinstance(actual_inputs, list):
        extra_inputs = actual_inputs[len(EXPECTED_PROFILE_INPUTS) :]
        metadata = cast(Mapping[str, Any], profile["additive_successor"])
        completed = cast(Mapping[str, Any], metadata["completed_input_successor"])
        inputs_valid = (
            input_projection[: len(EXPECTED_PROFILE_INPUTS)] == EXPECTED_PROFILE_INPUTS
            and len(extra_inputs) == 4
            and extra_inputs[0]
            == {
                "role": "completed_technical_input_additive_successor",
                "path": completed["path"],
                "sha256": completed["sha256"],
                "schema_or_type": "price_calculator_input_draft.v0.2",
                "purpose": "exact 15-group/112-row additive technical authority",
            }
            and extra_inputs[1:] == ADDITIVE_DECISION_BINDINGS
        )
    if shu_t2 and isinstance(actual_inputs, list):
        parent_profile = cast(Mapping[str, Any], profile["additive_successor"])
        parent_completed = cast(
            Mapping[str, Any], parent_profile["completed_input_successor"]
        )
        old_extra = [
            {
                "role": "completed_technical_input_additive_successor",
                "path": parent_completed["path"],
                "sha256": parent_completed["sha256"],
                "schema_or_type": V02_SCHEMA_VERSION,
                "purpose": "exact 15-group/112-row additive technical authority",
            },
            *ADDITIVE_DECISION_BINDINGS,
        ]
        metadata = cast(
            Mapping[str, Any], profile["shu_t2_rt820_pricing_profile_successor"]
        )
        new_extra = [
            {
                "role": "parent_pricing_profile_successor",
                **cast(Mapping[str, Any], metadata["parent_pricing_profile"]),
            },
            {
                "role": "completed_technical_input_shu_t2_rt820_successor",
                "path": cast(Mapping[str, Any], metadata["technical_successor"])[
                    "path"
                ],
                "sha256": cast(Mapping[str, Any], metadata["technical_successor"])[
                    "sha256"
                ],
                "schema_or_type": V02_SCHEMA_VERSION,
                "purpose": "exact 15-group/116-row SHU-T2 RT-820 technical authority",
            },
            {
                "role": "shu_t2_rt820_scope_human_decision",
                **cast(Mapping[str, Any], metadata["human_decision"]),
            },
            {
                "role": "main_price_workbook_shu_t2_rt820_revalidated",
                "path": cast(Mapping[str, Any], metadata["pricing_workbook"])["path"],
                "sha256": cast(Mapping[str, Any], metadata["pricing_workbook"])[
                    "sha256"
                ],
                "schema_or_type": cast(Mapping[str, Any], metadata["pricing_workbook"])[
                    "schema_or_type"
                ],
                "source_range": "КРН!A19:C19",
            },
        ]
        inputs_valid = input_projection[
            : len(EXPECTED_PROFILE_INPUTS)
        ] == EXPECTED_PROFILE_INPUTS and actual_inputs[
            len(EXPECTED_PROFILE_INPUTS) :
        ] == [
            *old_extra,
            *new_extra,
        ]
    checks.append(profile_check(result, inputs_valid, "authoritative inputs mismatch"))
    checks.append(validate_additive_profile_envelope(profile, result))
    checks.append(validate_shu_t2_profile_envelope(profile, result))
    checks.extend(
        validate_profile_policy_contract(
            profile,
            result,
            additive=additive or shu_t2,
            coverage=(SHU_T2_RT820_PROFILE_COVERAGE if shu_t2 else None),
        )
    )
    return all(checks)


def validate_profile_policy_contract(
    profile: Mapping[str, Any],
    result: CheckedRunResult,
    *,
    additive: bool = False,
    coverage: Mapping[str, int] | None = None,
) -> list[bool]:
    expected_coverage = (
        coverage
        if coverage is not None
        else (ADDITIVE_PROFILE_COVERAGE if additive else EXPECTED_PROFILE_COVERAGE)
    )
    expected_scope_partition = {
        "current_completed_technical_scope": {
            "technical_scope_status": "CURRENT_COMPLETED_INPUT_SCOPE",
            "pricing_profile_decision_status": "APPROVED_NOT_APPLIED",
            "pricing_calculation_status": "NOT_EXECUTED",
            "coverage": expected_coverage,
        },
        "reserved_case_level_formula_rules": {
            "formula_rule_status": "HUMAN_APPROVED_CASE_LEVEL_RULE_NOT_APPLIED",
            "technical_scope_status": (
                "NO_CONFIRMED_POSITION_IN_CURRENT_COMPLETED_INPUT"
            ),
            "application_status": "NOT_APPLIED",
            "excluded_from_current_coverage": True,
        },
    }
    expected_grain = {
        "unit": "section-aware priceable cabinet position / composition variant",
        "cabinet_group_is_technical_mapping_scope_not_automatic_unit_pricing": True,
        "unit_price_before_multiplicity": True,
        "cabinet_base_once_per_physical_cabinet": True,
        "multiplicity_after_unit_price_rounding": True,
        "cross_section_quantity_aggregation_before_unit_calculation": False,
        "completed_input_is_technical_authority": True,
        "pdf_or_invoice_override_applied_human_decisions": False,
    }
    expected_rounding = {
        "stage": "AFTER_FULL_UNIT_PRICE_FORMULA",
        "precision_kzt": 1,
        "mode": "ROUND_HALF_UP",
        "intermediate_rounding": False,
        "multiplicity_stage": "AFTER_UNIT_PRICE_ROUNDING",
        "invoice_manual_adjustment": False,
    }
    expected_tail = {
        "scope": "PROJECT_2024_086_INVOICE_519_ONLY",
        "formula": "*1.08765/1.16*1.2",
        "factor_1_08765_semantics": (
            "case-specific Igor correction instead of a separate general 1.2 mm "
            "metal thickness coefficient"
        ),
        "divide_1_16_semantics": "remove VAT because Invoice 519 is without VAT",
        "final_factor_1_2_semantics": "buyer representative bonus",
        "pre_tail_factors": ["1.25", "1.15"],
        "global_default": False,
        "unknown_other_project_factor_requires_igor_decision": True,
        "must_not_mix_with_internal_material_factor": True,
    }
    expected_safety = {
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
    }
    expected_non_approvals = {
        "project_total_approved": False,
        "remaining_current_position_prices_approved": False,
        "reserved_family_prices_approved": False,
        "lead_time_approved": False,
        "final_invoice_or_quote_approved": False,
        "client_send_authorized": False,
    }
    return [
        profile_check(
            result,
            profile.get("scope_partition") == expected_scope_partition,
            "scope partition mismatch",
        ),
        profile_check(
            result,
            profile.get("pricing_grain") == expected_grain,
            "pricing grain mismatch",
        ),
        profile_check(
            result,
            profile.get("rounding_policy") == expected_rounding,
            "rounding contract mismatch",
        ),
        profile_check(
            result,
            profile.get("external_pricing_tail") == expected_tail,
            "external tail mismatch",
        ),
        profile_check(
            result,
            profile.get("safety_flags") == expected_safety,
            "safety flags mismatch",
        ),
        profile_check(
            result,
            profile.get("non_approvals") == expected_non_approvals,
            "non-approval flags mismatch",
        ),
    ]


def string_for_csv(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def split_item_inputs(
    data: Mapping[str, Any],
    result: CheckedRunResult,
) -> list[ItemCalculatorInput]:
    calculator_format = data.get("calculator_input_format")
    items = data.get("items")
    if not isinstance(calculator_format, Mapping):
        add_red_flag(result, "calculator_input_format must be an object")
        return []
    if calculator_format.get("columns") != list(CALCULATOR_COLUMNS):
        add_red_flag(result, "calculator columns do not match calculator contract")
        return []
    rows = calculator_format.get("rows")
    if not isinstance(rows, list) or not rows:
        add_red_flag(result, "calculator rows must be a non-empty list")
        return []
    if not isinstance(items, list) or not items:
        add_red_flag(result, "items must be a non-empty list")
        return []
    if any(not isinstance(row, Mapping) for row in rows):
        add_red_flag(result, "calculator rows must contain only objects")
        return []

    item_inputs: list[ItemCalculatorInput] = []
    used_row_indexes: set[int] = set()
    item_keys: set[tuple[str, str]] = set()
    for item_index, item_value in enumerate(items):
        if not isinstance(item_value, Mapping):
            add_red_flag(result, f"item must be an object: items[{item_index}]")
            return []
        product_name = item_value.get("product_name")
        cabinet = item_value.get("cabinet")
        components = item_value.get("components")
        if not isinstance(product_name, str) or not isinstance(cabinet, Mapping):
            add_red_flag(result, f"item identity is incomplete: items[{item_index}]")
            return []
        cabinet_code = cabinet.get("cabinet_code")
        cabinet_label = cabinet.get("cabinet_label")
        if not isinstance(cabinet_code, str) or not isinstance(cabinet_label, str):
            add_red_flag(result, f"item cabinet is incomplete: items[{item_index}]")
            return []
        if not isinstance(components, list) or not components:
            add_red_flag(result, f"item components are empty: items[{item_index}]")
            return []

        item_key = (product_name, cabinet_code)
        if item_key in item_keys:
            add_red_flag(
                result,
                f"ambiguous item routing for product/cabinet: "
                f"{product_name} / {cabinet_code}; ask Igor",
            )
            return []
        item_keys.add(item_key)
        matching_rows = [
            (row_index, cast(Mapping[str, Any], row))
            for row_index, row in enumerate(rows)
            if cast(Mapping[str, Any], row).get("product_name") == product_name
            and cast(Mapping[str, Any], row).get("cabinet_code") == cabinet_code
        ]
        if len(matching_rows) != len(components):
            add_red_flag(
                result,
                f"item row/component count mismatch for {product_name}: "
                f"{len(matching_rows)} rows / {len(components)} components",
            )
            return []

        enhanced_rows: list[dict[str, Any]] = []
        for component_index, ((row_index, row), component) in enumerate(
            zip(matching_rows, components, strict=True)
        ):
            if not isinstance(component, Mapping):
                add_red_flag(
                    result,
                    f"component must be an object: items[{item_index}].components"
                    f"[{component_index}]",
                )
                return []
            component_label = component.get("component_label")
            expected_values = (
                component.get("component_code"),
                component.get("quantity"),
                component.get("install_type"),
            )
            row_values = (
                row.get("component_code"),
                row.get("component_qty"),
                row.get("install_type"),
            )
            if not isinstance(component_label, str) or row_values != expected_values:
                add_red_flag(
                    result,
                    f"item component audit mismatch for {product_name} at "
                    f"component {component_index + 1}",
                )
                return []
            enhanced = {column: row[column] for column in CALCULATOR_COLUMNS}
            enhanced["component_label"] = component_label
            enhanced["cabinet_label"] = cabinet_label
            enhanced_rows.append(enhanced)
            used_row_indexes.add(row_index)

        item_inputs.append(
            ItemCalculatorInput(
                product_name=product_name,
                cabinet_code=cabinet_code,
                rows=enhanced_rows,
            )
        )

    if used_row_indexes != set(range(len(rows))):
        add_red_flag(result, "calculator rows are not assigned to exactly one item")
        return []
    return item_inputs


def split_v02_item_inputs(
    data: Mapping[str, Any],
    result: CheckedRunResult,
) -> list[ItemCalculatorInput]:
    calculator_format = data.get("calculator_input_format")
    cabinet_groups = data.get("cabinet_groups")
    if not isinstance(calculator_format, Mapping) or not isinstance(
        cabinet_groups, list
    ):
        add_red_flag(result, "v0.2 calculator/cabinet groups are invalid")
        return []
    if calculator_format.get("columns") != list(CALCULATOR_COLUMNS):
        add_red_flag(result, "calculator columns do not match calculator contract")
        return []
    row_drafts = calculator_format.get("row_drafts")
    if not isinstance(row_drafts, list) or not row_drafts:
        add_red_flag(result, "v0.2 row_drafts must be a non-empty list")
        return []

    row_index: dict[str, Mapping[str, Any]] = {}
    for raw_row in row_drafts:
        if not isinstance(raw_row, Mapping):
            add_red_flag(result, "v0.2 row draft must be an object")
            return []
        row_id = raw_row.get("row_id")
        if not isinstance(row_id, str) or row_id in row_index:
            add_red_flag(result, "v0.2 row draft IDs must be unique strings")
            return []
        row_index[row_id] = cast(Mapping[str, Any], raw_row)

    item_inputs: list[ItemCalculatorInput] = []
    used_rows: set[str] = set()
    group_ids: set[str] = set()
    for raw_group in cabinet_groups:
        if not isinstance(raw_group, Mapping):
            add_red_flag(result, "v0.2 cabinet group must be an object")
            return []
        group_id = raw_group.get("cabinet_group_id")
        product_name = raw_group.get("product_name")
        cabinet_code = raw_group.get("cabinet_code")
        cabinet_label = raw_group.get("cabinet_label")
        row_ids = raw_group.get("row_draft_ids")
        if (
            not isinstance(group_id, str)
            or group_id in group_ids
            or not isinstance(product_name, str)
            or not isinstance(cabinet_code, str)
            or not isinstance(cabinet_label, str)
            or not isinstance(row_ids, list)
            or not row_ids
        ):
            add_red_flag(result, "v0.2 cabinet group identity is invalid")
            return []
        group_ids.add(group_id)
        if cabinet_code == CUSTOM_SCHE_CABINET_CODE and (
            product_name not in CUSTOM_SCHE_PRODUCT_NAMES
            or cabinet_label != CUSTOM_SCHE_CABINET_LABEL
            or raw_group.get("consumables_factor") != 1.2
        ):
            add_red_flag(result, f"custom ЩЭ identity mismatch for {group_id}")
            return []

        enhanced_rows: list[dict[str, Any]] = []
        for raw_row_id in row_ids:
            if not isinstance(raw_row_id, str) or raw_row_id in used_rows:
                add_red_flag(result, f"v0.2 duplicate row membership for {group_id}")
                return []
            row = row_index.get(raw_row_id)
            if row is None or row.get("cabinet_group_id") != group_id:
                add_red_flag(result, f"v0.2 row routing mismatch for {raw_row_id}")
                return []
            values = row.get("calculator_values")
            component_label = row.get("component_label")
            if not isinstance(values, Mapping) or not isinstance(component_label, str):
                add_red_flag(result, f"v0.2 row completion mismatch for {raw_row_id}")
                return []
            try:
                enhanced = {column: values[column] for column in CALCULATOR_COLUMNS}
            except KeyError as exc:
                add_red_flag(result, f"v0.2 row is missing column: {exc.args[0]}")
                return []
            if (
                enhanced["product_name"] != product_name
                or enhanced["cabinet_code"] != cabinet_code
                or enhanced["consumables_factor"] != raw_group.get("consumables_factor")
            ):
                add_red_flag(result, f"v0.2 row/group audit mismatch for {raw_row_id}")
                return []
            enhanced["component_label"] = component_label
            enhanced["cabinet_label"] = cabinet_label
            enhanced_rows.append(enhanced)
            used_rows.add(raw_row_id)
        item_inputs.append(
            ItemCalculatorInput(
                product_name=product_name,
                cabinet_code=cabinet_code,
                rows=enhanced_rows,
            )
        )
    if used_rows != set(row_index):
        add_red_flag(result, "v0.2 rows are not assigned to exactly one cabinet group")
        return []
    return item_inputs


def load_calculator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "calc_quote_price_draft_for_invoice519_runner",
        CALCULATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("price calculator module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical_composition_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
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
    payload = json.dumps(
        components,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_profile_formula_contract(
    current_scope: Mapping[str, Any],
    profile: Mapping[str, Any],
    result: CheckedRunResult,
) -> bool:
    additive = has_additive_scope(profile)
    modular = current_scope.get("modular_formula_family")
    sche = current_scope.get("sche_formula_family")
    expected_modular = {
        "scope_cabinet_group_ids": [
            *(f"CABINET-GROUP-{index:03d}" for index in range(1, 10)),
            "CABINET-GROUP-014",
            *(["CABINET-GROUP-015"] if additive else []),
        ],
        "material_factor": "1.2",
        "approved_formula": (
            "ROUND_HALF_UP((X + I + G*1.2 + H)*1.25*1.15*1.08765/1.16*1.2, 1 KZT)"
        ),
        "symbols": {
            "X": "exact cabinet base for the position",
            "I": (
                "approved additional cabinet cost; numeric 0 when no approved I exists"
            ),
            "G": "material total for one cabinet",
            "H": "work total for one cabinet",
        },
        "cabinet_bases_kzt": {
            "CAB-KURN-038-24": 12557,
            "CAB-KRN-18": 7678,
            "CAB-KRN-12": 6936,
            "CAB-KRN-24": 7985,
        },
    }
    expected_pr_anchors = [
        {
            "sections": ["9", "13"],
            "G_material_kzt": 14850,
            "H_work_kzt": 3024,
            "X_cabinet_base_kzt": 12557,
            "I_additional_cabinet_cost_kzt": 0,
            "raw_unit_price_kzt": "54023.13012607758620689655173",
            "approved_unit_price_kzt": 54023,
            "decision_status": "APPROVED_NOT_APPLIED",
            "invoice_comparator_kzt": 54019,
            "invoice_override_used": False,
        },
        {
            "sections": ["11", "15"],
            "G_material_kzt": 17050,
            "H_work_kzt": 3564,
            "X_cabinet_base_kzt": 12557,
            "I_additional_cabinet_cost_kzt": 0,
            "raw_unit_price_kzt": "59166.49570797413793103448277",
            "approved_unit_price_kzt": 59166,
            "decision_status": "APPROVED_NOT_APPLIED",
            "invoice_comparator_kzt": 59163,
            "invoice_override_used": False,
        },
    ]
    expected_sche_prices = [
        {
            "product_name": product,
            "apartment_count": apartments,
            "G_material_kzt": 3200 * apartments,
            "H_work_kzt": 864 * apartments,
            "apartment_component_kzt": 5100 * apartments,
            "raw_unit_price_kzt": raw,
            "approved_unit_price_kzt": approved,
            "decision_status": "APPROVED_NOT_APPLIED",
        }
        for product, apartments, raw, approved in (
            ("ЩЭ-3кв", 3, "80412.80082866379310344827588", 80413),
            ("ЩЭ-4кв", 4, "96269.89396228448275862068967", 96270),
            ("ЩЭ-5кв", 5, "112126.9870959051724137931035", 112127),
            ("ЩЭ-6кв", 6, "127984.0802295258620689655173", 127984),
        )
    ]
    sche_contract_ok = isinstance(sche, Mapping) and all(
        (
            sche.get("scope_products") == list(EXPECTED_SCHE_APARTMENTS),
            sche.get("cabinet_code") == CUSTOM_SCHE_CABINET_CODE,
            sche.get("cabinet_base_kzt") == 20305,
            sche.get("cabinet_base_raw_kzt") == "20304.41634565600",
            sche.get("cabinet_base_rounding") == "ROUND_UP_TO_1_KZT",
            sche.get("physical_identity")
            == {"dimensions_mm": [900, 900, 120], "metal_thickness_mm": "1.2"},
            sche.get("prohibited_cached_base_kzt") == 18762,
            sche.get("material_factor") == "1.2",
            sche.get("apartment_component_kzt_per_apartment") == 5100,
            sche.get("apartment_component_formula") == "850*6",
            sche.get("approved_formula")
            == (
                "ROUND_HALF_UP((20305 + G*1.2 + H + "
                "5100*apartment_count)*1.25*1.15*1.08765/1.16*1.2, 1 KZT)"
            ),
            sche.get("existing_workbook_baseline_formula")
            == "J2+(G2+H2+(850*6*I2))*1.25*1.15",
            sche.get("case_profile_decision_is_not_inferred_from_workbook_baseline")
            is True,
            sche.get("approved_calculated_unit_prices") == expected_sche_prices,
        )
    )
    reserved = profile.get("reserved_case_level_formula_rules")
    reserved_ok = isinstance(reserved, list) and [
        item.get("family") for item in reserved if isinstance(item, Mapping)
    ] == list(EXPECTED_RESERVED_FAMILIES)
    if reserved_ok:
        for item in reserved:
            if not isinstance(item, Mapping):
                reserved_ok = False
                break
            family = item["family"]
            common_ok = (
                item.get("formula_rule_status")
                == "HUMAN_APPROVED_CASE_LEVEL_RULE_NOT_APPLIED"
                and item.get("technical_scope_status")
                == "NO_CONFIRMED_POSITION_IN_CURRENT_COMPLETED_INPUT"
                and item.get("application_status") == "NOT_APPLIED"
            )
            if family == "ВРУ-ВА":
                family_ok = (
                    item.get("material_factor") == "1.2"
                    and item.get("work_formula_cell") == "ВРУ-ВА!H2"
                    and item.get("work_formula") == "SUM(component work)+3000"
                    and item.get("fixed_work_adjustment_kzt") == 3000
                    and item.get("fixed_work_adjustment_semantics")
                    == "unlabelled fixed work adjustment"
                    and item.get("approved_case_formula")
                    == (
                        "ROUND_HALF_UP((X + I + G*1.2 + H)*1.25*1.15*"
                        "1.08765/1.16*1.2, 1 KZT)"
                    )
                )
            else:
                family_ok = (
                    item.get("material_factor") == "1.05"
                    and item.get("workbook_formula_cell") == f"{family}!H2"
                    and item.get("workbook_formula") == "(G2+E2*1.05+F2)*1.25*1.15"
                    and item.get("approved_case_formula")
                    == (
                        "ROUND_HALF_UP((X + I + G*1.05 + H)*1.25*1.15*"
                        "1.08765/1.16*1.2, 1 KZT)"
                    )
                )
            if not common_ok or not family_ok:
                reserved_ok = False
                break
    shu_t1_expected = {
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
    return all(
        (
            profile_check(
                result,
                modular == expected_modular,
                "modular formula contract mismatch",
            ),
            profile_check(
                result,
                sche_contract_ok,
                "custom ЩЭ formula contract mismatch",
            ),
            profile_check(
                result,
                current_scope.get("pr_approved_calculated_unit_prices")
                == expected_pr_anchors,
                "PR formula anchors mismatch",
            ),
            profile_check(
                result,
                reserved_ok,
                "reserved formula contract mismatch",
            ),
            profile_check(
                result,
                (
                    current_scope.get("shu_t1_approved_calculated_price")
                    == shu_t1_expected
                    if additive
                    else "shu_t1_approved_calculated_price" not in current_scope
                ),
                "ШУ-Т1 formula/rounding/multiplicity contract mismatch",
            ),
        )
    )


def profile_row_index(
    data: Mapping[str, Any],
    result: CheckedRunResult,
) -> tuple[list[Mapping[str, Any]], dict[str, Mapping[str, Any]]] | None:
    calculator_format = data.get("calculator_input_format")
    if not isinstance(calculator_format, Mapping):
        add_red_flag(result, "profile completed calculator format is invalid")
        return None
    rows = calculator_format.get("row_drafts")
    source = data.get("source")
    shu_t2 = isinstance(source, Mapping) and isinstance(
        source.get("shu_t2_rt820_technical_successor"), Mapping
    )
    additive = isinstance(source, Mapping) and isinstance(
        source.get("additive_completed_input_successor"), Mapping
    )
    expected_rows = 116 if shu_t2 else (112 if additive else 109)
    if not isinstance(rows, list) or len(rows) != expected_rows:
        add_red_flag(
            result, f"profile requires exact {expected_rows} completed row drafts"
        )
        return None
    typed_rows: list[Mapping[str, Any]] = []
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            add_red_flag(result, "profile completed row draft must be an object")
            return None
        row_id = row.get("row_id")
        if not isinstance(row_id, str) or row_id in indexed:
            add_red_flag(result, "profile completed row IDs must be unique strings")
            return None
        typed_rows.append(cast(Mapping[str, Any], row))
        indexed[row_id] = cast(Mapping[str, Any], row)
    return typed_rows, indexed


def validate_exact_shu_t2_replacement(
    current_scope: Mapping[str, Any], result: CheckedRunResult
) -> bool:
    groups = current_scope.get("cabinet_groups")
    positions = current_scope.get("pricing_positions")
    fingerprints = current_scope.get("composition_fingerprints")
    if not (
        isinstance(groups, list)
        and len(groups) == 15
        and isinstance(positions, list)
        and len(positions) == 55
        and isinstance(fingerprints, list)
        and len(fingerprints) == 11
    ):
        return profile_check(result, False, "SHU-T2 replacement inventory mismatch")
    expected = (
        ("PRICE-POSITION-009", "TFE-016", "ROW-DRAFT-0113", 112),
        ("PRICE-POSITION-023", "TFE-041", "ROW-DRAFT-0114", 113),
        ("PRICE-POSITION-035", "TFE-061", "ROW-DRAFT-0115", 114),
        ("PRICE-POSITION-047", "TFE-083", "ROW-DRAFT-0116", 115),
    )
    by_position = {
        item.get("pricing_position_id"): item
        for item in positions
        if isinstance(item, Mapping)
    }
    target_ids = {item[0] for item in expected}
    new_rows = {item[2] for item in expected}
    valid = all(
        (
            current_scope.get("coverage") == SHU_T2_RT820_PROFILE_COVERAGE,
            sum(
                item.get("physical_multiplicity", 0)
                for item in positions
                if isinstance(item, Mapping)
            )
            == 137,
            groups[2].get("cabinet_group_id") == "CABINET-GROUP-003",
            groups[2].get("product_name") == "ШУ-Т2",
            groups[2].get("row_draft_ids")[-4:] == [item[2] for item in expected],
            len(groups[2].get("row_draft_ids", [])) == 12,
            all(
                isinstance(by_position.get(position_id), Mapping)
                and by_position[position_id].get("source_position_id") == source_id
                and by_position[position_id].get("cabinet_group_id")
                == "CABINET-GROUP-003"
                and by_position[position_id].get("product_name") == "ШУ-Т2"
                and by_position[position_id].get("row_draft_ids")[-1] == row_id
                and by_position[position_id].get("row_draft_json_paths")[-1]
                == f"$.calculator_input_format.row_drafts[{row_index}]"
                and by_position[position_id].get("composition_fingerprint_sha256")
                == SHU_T1_FINGERPRINT
                and by_position[position_id].get("approved_unit_price_kzt") is None
                and by_position[position_id].get("approved_unit_price_decision_status")
                == "NOT_CALCULATED_NOT_APPROVED"
                for position_id, source_id, row_id, row_index in expected
            ),
            all(
                not new_rows.intersection(item.get("row_draft_ids", []))
                for item in positions
                if isinstance(item, Mapping)
                and item.get("pricing_position_id") not in target_ids
            ),
        )
    )
    old_fingerprint = "99db78a5c3c7688a9e2cebbbe57f41489af797bbc61f2b1fa38492a42329cb79"
    fingerprint_ids = [
        item.get("fingerprint_sha256")
        for item in fingerprints
        if isinstance(item, Mapping)
    ]
    merged = next(
        (
            item
            for item in fingerprints
            if isinstance(item, Mapping)
            and item.get("fingerprint_sha256") == SHU_T1_FINGERPRINT
        ),
        None,
    )
    valid = valid and all(
        (
            old_fingerprint not in fingerprint_ids,
            fingerprint_ids.count(SHU_T1_FINGERPRINT) == 1,
            isinstance(merged, Mapping),
            isinstance(merged, Mapping)
            and merged.get("source_position_ids")
            == [
                "TFE-016",
                "TFE-041",
                "TFE-061",
                "TFE-083",
                "TFE-006",
                "TFE-029",
                "TFE-052",
                "TFE-074",
            ],
            isinstance(merged, Mapping)
            and merged.get("pricing_position_ids")
            == [
                "PRICE-POSITION-009",
                "PRICE-POSITION-023",
                "PRICE-POSITION-035",
                "PRICE-POSITION-047",
                "PRICE-POSITION-052",
                "PRICE-POSITION-053",
                "PRICE-POSITION-054",
                "PRICE-POSITION-055",
            ],
        )
    )
    candidate = current_scope.get("shu_t2_rt820_preliminary_candidate")
    valid = valid and candidate == {
        "status": "NOT_CALCULATED_NOT_APPROVED",
        "approved_unit_price_kzt": None,
        "application_status": "NOT_APPLIED",
        "unit_candidate_kzt": 53763,
        "four_position_candidate_kzt": 215052,
        "preliminary_project_candidate_kzt": 11963792,
    }
    return profile_check(result, valid, "exact SHU-T2 controlled replacement mismatch")


def validate_and_build_profile_positions(
    data: Mapping[str, Any],
    profile: Mapping[str, Any],
    result: CheckedRunResult,
) -> list[ProfilePositionInput]:
    if data.get("schema_version") != V02_SCHEMA_VERSION:
        add_red_flag(result, "Invoice 519 profile requires completed v0.2 input")
        return []
    additive_metadata = additive_profile_metadata(profile)
    shu_t2_metadata = shu_t2_profile_metadata(profile)
    additive = additive_metadata is not None or shu_t2_metadata is not None
    if shu_t2_metadata is not None:
        source = data.get("source")
        technical_metadata = (
            source.get("shu_t2_rt820_technical_successor")
            if isinstance(source, Mapping)
            else None
        )
        completed_binding = shu_t2_metadata.get("technical_successor")
        human_binding = (
            technical_metadata.get("human_decision")
            if isinstance(technical_metadata, Mapping)
            else None
        )
        bindings_ok = all(
            (
                isinstance(technical_metadata, Mapping),
                isinstance(technical_metadata, Mapping)
                and technical_metadata.get("contract")
                == SHU_T2_RT820_TECHNICAL_CONTRACT,
                isinstance(technical_metadata, Mapping)
                and technical_metadata.get("scope_expansion") is False,
                isinstance(human_binding, Mapping),
                isinstance(human_binding, Mapping)
                and human_binding.get("sha256") == SHU_T2_RT820_DECISION_SHA256,
                isinstance(completed_binding, Mapping),
                isinstance(completed_binding, Mapping)
                and resolved(Path(cast(str, completed_binding.get("path", ""))))
                == result.completed_input_json,
                isinstance(completed_binding, Mapping)
                and completed_binding.get("sha256") == SHU_T2_RT820_TECHNICAL_SHA256,
                isinstance(completed_binding, Mapping)
                and completed_binding.get("contract")
                == SHU_T2_RT820_TECHNICAL_CONTRACT,
            )
        )
        if not profile_check(
            result, bindings_ok, "SHU-T2 technical/profile successor binding mismatch"
        ):
            return []
    elif additive_metadata is not None:
        source = data.get("source")
        technical_metadata = (
            source.get("additive_completed_input_successor")
            if isinstance(source, Mapping)
            else None
        )
        completed_binding = additive_metadata.get("completed_input_successor")
        additive_bindings_ok = all(
            (
                isinstance(technical_metadata, Mapping),
                isinstance(technical_metadata, Mapping)
                and technical_metadata.get("contract") == ADDITIVE_COMPLETED_CONTRACT,
                isinstance(technical_metadata, Mapping)
                and technical_metadata.get("direct_human_decision_inputs")
                == ADDITIVE_DECISION_BINDINGS,
                isinstance(technical_metadata, Mapping)
                and technical_metadata.get("scope_expansion") is False,
                isinstance(completed_binding, Mapping),
                isinstance(completed_binding, Mapping)
                and resolved(Path(cast(str, completed_binding.get("path", ""))))
                == result.completed_input_json,
                isinstance(completed_binding, Mapping)
                and completed_binding.get("contract") == ADDITIVE_COMPLETED_CONTRACT,
            )
        )
        if not profile_check(
            result, additive_bindings_ok, "technical/profile successor binding mismatch"
        ):
            return []
    row_indexes = profile_row_index(data, result)
    if row_indexes is None:
        return []
    rows, rows_by_id = row_indexes
    completed_groups = data.get("cabinet_groups")
    current_scope = profile.get("current_completed_technical_scope")
    if not isinstance(completed_groups, list) or not isinstance(current_scope, Mapping):
        add_red_flag(result, "profile current technical scope is invalid")
        return []
    profile_groups = current_scope.get("cabinet_groups")
    positions = current_scope.get("pricing_positions")
    fingerprints = current_scope.get("composition_fingerprints")
    if (
        not isinstance(profile_groups, list)
        or not isinstance(positions, list)
        or not isinstance(fingerprints, list)
    ):
        add_red_flag(result, "profile inventory lists are invalid")
        return []
    if shu_t2_metadata is not None and not validate_exact_shu_t2_replacement(
        current_scope, result
    ):
        return []
    expected_coverage = (
        SHU_T2_RT820_PROFILE_COVERAGE
        if shu_t2_metadata is not None
        else (ADDITIVE_PROFILE_COVERAGE if additive else EXPECTED_PROFILE_COVERAGE)
    )
    expected_products = (
        ADDITIVE_PROFILE_PRODUCTS if additive else EXPECTED_PROFILE_PRODUCTS
    )
    expected_groups = 15 if additive else 14
    expected_positions = 55 if additive else 51
    expected_fingerprints_count = (
        11 if shu_t2_metadata is not None else (12 if additive else 11)
    )
    expected_multiplicity = 137 if additive else 133
    inventory_ok = all(
        (
            current_scope.get("coverage") == expected_coverage,
            current_scope.get("products") == expected_products,
            len(completed_groups) == expected_groups,
            len(profile_groups) == expected_groups,
            len(positions) == expected_positions,
            len(fingerprints) == expected_fingerprints_count,
        )
    )
    inventory_label = (
        "15/55/137/11"
        if shu_t2_metadata is not None
        else ("15/55/137/12" if additive else "14/51/133/11")
    )
    if not profile_check(result, inventory_ok, f"{inventory_label} inventory mismatch"):
        return []
    if not validate_profile_formula_contract(current_scope, profile, result):
        return []

    groups: dict[str, Mapping[str, Any]] = {}
    for index, (raw_completed, raw_profile) in enumerate(
        zip(completed_groups, profile_groups, strict=True)
    ):
        expected_group_id = f"CABINET-GROUP-{index + 1:03d}"
        if not isinstance(raw_completed, Mapping) or not isinstance(
            raw_profile, Mapping
        ):
            add_red_flag(result, "profile cabinet group must be an object")
            return []
        formula_family = (
            "CURRENT_SCHE_CASE_PROFILE"
            if raw_profile.get("cabinet_code") == CUSTOM_SCHE_CABINET_CODE
            else "CURRENT_MODULAR_CASE_PROFILE"
        )
        expected_base = {
            "CAB-KURN-038-24": 12557,
            "CAB-KRN-18": 7678,
            "CAB-KRN-12": 6936,
            "CAB-KRN-24": 7985,
            CUSTOM_SCHE_CABINET_CODE: 20305,
        }.get(raw_profile.get("cabinet_code"))
        matches = all(
            (
                raw_profile.get("cabinet_group_id") == expected_group_id,
                raw_completed.get("cabinet_group_id") == expected_group_id,
                raw_profile.get("completed_input_json_path")
                == f"$.cabinet_groups[{index}]",
                raw_profile.get("source_cabinet_template")
                == raw_completed.get("source_cabinet_template"),
                raw_profile.get("product_name") == raw_completed.get("product_name"),
                raw_profile.get("cabinet_code") == raw_completed.get("cabinet_code"),
                raw_profile.get("row_draft_ids") == raw_completed.get("row_draft_ids"),
                raw_profile.get("formula_family") == formula_family,
                raw_profile.get("cabinet_base_kzt") == expected_base,
                raw_profile.get("approved_additional_cabinet_cost_kzt") == 0,
            )
        )
        if not profile_check(
            result,
            matches,
            f"cabinet group drift at {expected_group_id}",
        ):
            return []
        groups[expected_group_id] = cast(Mapping[str, Any], raw_profile)

    position_inputs: list[ProfilePositionInput] = []
    derived_fingerprints: dict[str, dict[str, Any]] = {}
    total_multiplicity = 0
    for index, raw_position in enumerate(positions):
        expected_position_id = f"PRICE-POSITION-{index + 1:03d}"
        if not isinstance(raw_position, Mapping):
            add_red_flag(result, "profile position must be an object")
            return []
        group_id = raw_position.get("cabinet_group_id")
        group = groups.get(group_id) if isinstance(group_id, str) else None
        row_ids = raw_position.get("row_draft_ids")
        row_paths = raw_position.get("row_draft_json_paths")
        if (
            group is None
            or not isinstance(row_ids, list)
            or not isinstance(row_paths, list)
        ):
            add_red_flag(
                result,
                f"profile position scope is invalid at {expected_position_id}",
            )
            return []
        selected_rows: list[Mapping[str, Any]] = []
        for row_id, row_path in zip(row_ids, row_paths, strict=False):
            if not isinstance(row_id, str) or row_id not in rows_by_id:
                add_red_flag(
                    result,
                    f"profile row scope mismatch at {expected_position_id}",
                )
                return []
            row = rows_by_id[row_id]
            row_index = rows.index(row)
            if row_path != f"$.calculator_input_format.row_drafts[{row_index}]":
                add_red_flag(
                    result,
                    f"profile row path mismatch at {expected_position_id}",
                )
                return []
            selected_rows.append(row)
        if len(selected_rows) != len(row_ids) or len(row_ids) != len(row_paths):
            add_red_flag(
                result,
                f"profile row order mismatch at {expected_position_id}",
            )
            return []
        source_position_id = raw_position.get("source_position_id")
        source_position_number = (
            int(source_position_id.removeprefix("TFE-"))
            if isinstance(source_position_id, str)
            and source_position_id.startswith("TFE-")
            and source_position_id.removeprefix("TFE-").isdigit()
            else 0
        )
        section = raw_position.get("section")
        discipline = raw_position.get("discipline")
        source_document = raw_position.get("source_document")
        multiplicity = raw_position.get("physical_multiplicity")
        fingerprint = canonical_composition_fingerprint(selected_rows)
        invoice_comparator = raw_position.get("invoice_comparator")
        position_ok = all(
            (
                raw_position.get("pricing_position_id") == expected_position_id,
                raw_position.get("technical_scope_status")
                == "CURRENT_COMPLETED_INPUT_SCOPE",
                isinstance(section, str),
                isinstance(discipline, str) and discipline in {"ЭОМ", "ЭОФ"},
                isinstance(source_document, Mapping),
                (
                    source_document.get("document_id")
                    == f"Секция {section}_{discipline}.pdf"
                    if isinstance(source_document, Mapping)
                    else False
                ),
                isinstance(source_document, Mapping)
                and isinstance(source_document.get("sha256"), str)
                and len(source_document["sha256"]) == 64,
                source_position_number > 0,
                raw_position.get("source_position_json_path")
                == f"$.positions[{source_position_number - 1}]",
                raw_position.get("cabinet_group_json_path")
                == f"$.cabinet_groups[{int(group_id[-3:]) - 1}]",
                raw_position.get("product_name") == group.get("product_name"),
                raw_position.get("cabinet_code") == group.get("cabinet_code"),
                all(row.get("cabinet_group_id") == group_id for row in selected_rows),
                all(
                    isinstance(row.get("calculator_values"), Mapping)
                    and row["calculator_values"].get("product_name")
                    == group.get("product_name")
                    and row["calculator_values"].get("cabinet_code")
                    == group.get("cabinet_code")
                    for row in selected_rows
                ),
                raw_position.get("composition_fingerprint_sha256") == fingerprint,
                isinstance(multiplicity, int)
                and not isinstance(multiplicity, bool)
                and multiplicity > 0,
                raw_position.get("unit_pricing_before_multiplicity") is True,
                isinstance(invoice_comparator, Mapping)
                and invoice_comparator.get("manual_override_used") is False,
                raw_position.get("pricing_calculation_status") == "NOT_EXECUTED",
            )
        )
        if not profile_check(
            result,
            position_ok,
            f"position drift at {expected_position_id}",
        ):
            return []
        product_name = cast(str, group["product_name"])
        apartment_count = EXPECTED_SCHE_APARTMENTS.get(product_name)
        approved_price = raw_position.get("approved_unit_price_kzt")
        expected_decision_status = (
            "APPROVED_NOT_APPLIED"
            if product_name in {"ПР", "ШУ-Т1"} or apartment_count is not None
            else "NOT_CALCULATED_NOT_APPROVED"
        )
        if not profile_check(
            result,
            raw_position.get("approved_unit_price_decision_status")
            == expected_decision_status
            and (
                isinstance(approved_price, int)
                if expected_decision_status == "APPROVED_NOT_APPLIED"
                else approved_price is None
            ),
            f"approved-price scope mismatch at {expected_position_id}",
        ):
            return []
        components = sorted(
            (
                {
                    "component_code": row["calculator_values"]["component_code"],
                    "component_qty": row["calculator_values"]["component_qty"],
                    "install_type": row["calculator_values"]["install_type"],
                }
                for row in selected_rows
            ),
            key=lambda item: (
                item["component_code"],
                item["component_qty"],
                item["install_type"],
            ),
        )
        derived = derived_fingerprints.setdefault(
            fingerprint,
            {
                "fingerprint_sha256": fingerprint,
                "canonicalization": (
                    "SHA256 UTF-8 canonical JSON of sorted "
                    "component_code/component_qty/install_type tuples"
                ),
                "components": components,
                "source_position_ids": [],
                "pricing_position_ids": [],
            },
        )
        if derived["components"] != components:
            add_red_flag(result, f"fingerprint collision at {expected_position_id}")
            return []
        derived["source_position_ids"].append(source_position_id)
        derived["pricing_position_ids"].append(expected_position_id)
        total_multiplicity += cast(int, multiplicity)
        enhanced_rows = []
        completed_group = cast(
            Mapping[str, Any], completed_groups[int(cast(str, group_id)[-3:]) - 1]
        )
        for row in selected_rows:
            values = row["calculator_values"]
            enhanced = {column: values[column] for column in CALCULATOR_COLUMNS}
            enhanced["component_label"] = row["component_label"]
            enhanced["cabinet_label"] = completed_group["cabinet_label"]
            if shu_t2_metadata is not None:
                enhanced.update(
                    {
                        "technical_successor_contract": (
                            SHU_T2_RT820_TECHNICAL_CONTRACT
                        ),
                        "technical_successor_sha256": (SHU_T2_RT820_TECHNICAL_SHA256),
                        "pricing_profile_contract": SHU_T2_RT820_PROFILE_CONTRACT,
                        "pricing_profile_sha256": SHU_T2_RT820_PROFILE_SHA256,
                        "human_decision_sha256": SHU_T2_RT820_DECISION_SHA256,
                    }
                )
            enhanced_rows.append(enhanced)
        position_inputs.append(
            ProfilePositionInput(
                pricing_position_id=expected_position_id,
                section=cast(str, section),
                discipline=cast(str, discipline),
                source_document=cast(Mapping[str, Any], source_document),
                cabinet_group_id=cast(str, group_id),
                product_name=product_name,
                cabinet_code=cast(str, group["cabinet_code"]),
                formula_family=cast(str, group["formula_family"]),
                row_draft_ids=cast(list[str], row_ids),
                rows=enhanced_rows,
                composition_fingerprint_sha256=fingerprint,
                physical_multiplicity=cast(int, multiplicity),
                apartment_count=apartment_count,
                approved_unit_price_kzt=(
                    cast(int, approved_price)
                    if isinstance(approved_price, int)
                    else None
                ),
                cabinet_base_kzt=cast(int, group["cabinet_base_kzt"]),
                additional_cabinet_cost_kzt=cast(
                    int, group["approved_additional_cabinet_cost_kzt"]
                ),
            )
        )
    expected_fingerprints = [
        derived_fingerprints[key]
        for key in sorted(
            key
            for key in derived_fingerprints
            if not additive or key != SHU_T1_FINGERPRINT
        )
    ]
    if additive and SHU_T1_FINGERPRINT in derived_fingerprints:
        expected_fingerprints.append(derived_fingerprints[SHU_T1_FINGERPRINT])
    final_ok = all(
        (
            total_multiplicity == expected_multiplicity,
            len(derived_fingerprints) == expected_fingerprints_count,
            fingerprints == expected_fingerprints,
            {
                row_id
                for position in position_inputs
                for row_id in position.row_draft_ids
            }
            == set(rows_by_id),
        )
    )
    if not profile_check(result, final_ok, "position coverage/fingerprint mismatch"):
        return []
    return position_inputs


def create_csv_bridge(
    item_input: ItemCalculatorInput,
    result: CheckedRunResult,
) -> Path | None:
    temp_handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        suffix=".csv",
        prefix="checked_price_calculator_",
        delete=False,
    )
    temp_path = Path(temp_handle.name)
    if result.temp_csv_path is None:
        result.temp_csv_path = temp_path
    result.temp_csv_paths.append(temp_path)
    result.temp_csv_deleted = False

    try:
        if is_inside_project(temp_path):
            add_red_flag(result, "temporary CSV bridge must be outside the project")
            return None

        with temp_handle:
            columns = (
                SHU_T2_TECHNICAL_CALCULATOR_COLUMNS
                if item_input.rows
                and all(
                    column in item_input.rows[0]
                    for column in SHU_T2_RT820_BINDING_COLUMNS
                )
                else TECHNICAL_CALCULATOR_COLUMNS
            )
            writer = csv.writer(
                temp_handle,
                delimiter=CSV_DELIMITER,
                lineterminator="\n",
            )
            writer.writerow(columns)
            for row in item_input.rows:
                writer.writerow([string_for_csv(row[column]) for column in columns])
    except OSError:
        add_red_flag(result, "temporary CSV bridge could not be written")
        return None
    except KeyError as exc:
        add_red_flag(result, f"calculator row is missing column: {exc.args[0]}")
        return None

    return temp_path


def load_custom_sche_resolver_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "resolve_custom_sche_cabinet_base_cost_for_checked_runner",
        CUSTOM_SCHE_RESOLVER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("custom ЩЭ resolver could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def resolve_custom_sche_base_cost(metal_workbook: Path) -> int:
    resolver = load_custom_sche_resolver_module()
    resolution = resolver.resolve_custom_sche_cabinet_base_cost(
        metal_workbook_path=resolved(metal_workbook),
        expected_workbook_sha256=resolver.APPROVED_WORKBOOK_SHA256,
        internal_cabinet_code=resolver.APPROVED_INTERNAL_CABINET_CODE,
        metal_thickness=str(resolver.APPROVED_METAL_THICKNESS),
        expected_sheet=resolver.APPROVED_SHEET,
        expected_row=resolver.APPROVED_ROW,
    )
    if resolution.get("status") != "CUSTOM_SCHE_BASE_COST_RESOLUTION_VALIDATED":
        raise RuntimeError("custom ЩЭ resolver failed closed")
    base_cost = resolution.get("base_cost")
    if not isinstance(base_cost, Mapping):
        raise RuntimeError("custom ЩЭ resolver base_cost is missing")
    value = base_cost.get("value")
    if not isinstance(value, str) or not value.isdigit() or int(value) <= 0:
        raise RuntimeError("custom ЩЭ resolver base_cost is invalid")
    return int(value)


def run_calculator_cli(
    price_workbook: Path,
    input_csv: Path,
    custom_cabinet_base_cost: int | None = None,
) -> CalculatorProcessResult:
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"
    command = [
        sys.executable,
        str(CALCULATOR_PATH),
        "--price-workbook",
        str(price_workbook),
        "--input-csv",
        str(input_csv),
    ]
    if custom_cabinet_base_cost is not None:
        command.extend(["--custom-cabinet-base-cost", str(custom_cabinet_base_cost)])
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=child_env,
        check=False,
    )
    return CalculatorProcessResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def parse_calculator_fields(stdout: str) -> dict[str, str]:
    lines = stdout.splitlines()
    fields: dict[str, str] = {}
    for index, line in enumerate(lines):
        key = line.removesuffix(":")
        if key in CALCULATOR_SUMMARY_KEYS and index + 1 < len(lines):
            fields[key] = lines[index + 1]
    return fields


def parse_report_integer(value: str) -> int | None:
    compact = value.replace(" ", "")
    return int(compact) if compact.isdigit() else None


def profile_input_role_map(profile: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw_inputs = profile.get("authoritative_inputs")
    if not isinstance(raw_inputs, list):
        return {}
    return {
        cast(str, item["role"]): cast(Mapping[str, Any], item)
        for item in raw_inputs
        if isinstance(item, Mapping) and isinstance(item.get("role"), str)
    }


def capture_profile_input_shas(
    result: CheckedRunResult,
    profile: Mapping[str, Any],
    pricing_profile_path: Path,
    custom_sche_metal_workbook: Path | None,
    pricing_profile_sha256: str | None = None,
) -> dict[str, tuple[Path, str]] | None:
    roles = profile_input_role_map(profile)
    if custom_sche_metal_workbook is None:
        add_red_flag(result, "custom ЩЭ metal workbook is required by pricing profile")
        return None
    if pricing_profile_sha256 is None:
        pricing_profile_sha256 = PRICING_PROFILE_SHA256
    shu_t2 = shu_t2_profile_metadata(profile) is not None
    additive = additive_profile_metadata(profile) is not None and not shu_t2
    completed_role = (
        "completed_technical_input_shu_t2_rt820_successor"
        if shu_t2
        else (
            "completed_technical_input_additive_successor"
            if additive
            else "completed_technical_input"
        )
    )
    requested = {
        "pricing_profile": (
            resolved(pricing_profile_path),
            pricing_profile_sha256,
        ),
        completed_role: (
            result.completed_input_json,
            roles.get(completed_role, {}).get("sha256"),
        ),
        "main_price_workbook": (
            result.price_workbook,
            roles.get("main_price_workbook", {}).get("sha256"),
        ),
        "custom_sche_metal_workbook": (
            resolved(custom_sche_metal_workbook),
            roles.get("custom_sche_metal_workbook", {}).get("sha256"),
        ),
    }
    if additive:
        for binding in ADDITIVE_DECISION_BINDINGS:
            role = cast(str, binding["role"])
            requested[role] = (
                resolved(Path(cast(str, binding["path"]))),
                cast(str, binding["sha256"]),
            )
    if shu_t2:
        for role in (
            "parent_pricing_profile_successor",
            "shu_t2_rt820_scope_human_decision",
            "main_price_workbook_shu_t2_rt820_revalidated",
        ):
            requested[role] = (
                resolved(Path(cast(str, roles.get(role, {}).get("path", "")))),
                roles.get(role, {}).get("sha256"),
            )
    for role, (path, expected_sha) in requested.items():
        expected_path = (
            pricing_profile_path
            if role == "pricing_profile"
            else Path(cast(str, roles.get(role, {}).get("path", "")))
        )
        if path != resolved(expected_path) or not isinstance(expected_sha, str):
            add_red_flag(result, f"{role} path/lineage mismatch")
            return None
        try:
            actual_sha = sha256_file(path)
        except OSError:
            add_red_flag(result, f"{role} could not be read for initial SHA check")
            return None
        if actual_sha != expected_sha:
            add_red_flag(result, f"{role} initial SHA-256 mismatch")
            return None
        result.input_sha_provenance[role] = actual_sha
    return {
        role: (path, cast(str, expected_sha))
        for role, (path, expected_sha) in requested.items()
    }


def recheck_profile_input_shas(
    result: CheckedRunResult,
    snapshots: Mapping[str, tuple[Path, str]],
    stage: str,
) -> bool:
    for role, (path, expected_sha) in snapshots.items():
        try:
            actual_sha = sha256_file(path)
        except OSError:
            add_red_flag(result, f"{role} could not be read during {stage} SHA recheck")
            return False
        if actual_sha != expected_sha:
            add_red_flag(result, f"{role} drift during {stage} SHA recheck")
            return False
    return True


def parse_calculator_red_flags(stdout: str) -> list[str]:
    lines = stdout.splitlines()
    try:
        start = lines.index("Red flags:") + 1
    except ValueError:
        return []

    red_flags: list[str] = []
    for line in lines[start:]:
        if not line.strip():
            break
        if line.strip().casefold() != "none":
            red_flags.append(line)
    return red_flags


def execute_calculator(
    result: CheckedRunResult,
    item_input: ItemCalculatorInput,
    input_csv: Path,
    custom_cabinet_base_cost: int | None = None,
) -> bool:
    try:
        process_result = (
            run_calculator_cli(result.price_workbook, input_csv)
            if custom_cabinet_base_cost is None
            else run_calculator_cli(
                result.price_workbook,
                input_csv,
                custom_cabinet_base_cost=custom_cabinet_base_cost,
            )
        )
    except OSError:
        add_red_flag(result, "calculator invocation failed")
        return False

    result.calculator_runs.append(process_result)
    result.calculator_returncode = process_result.returncode
    result.calculator_stdout = process_result.stdout
    result.calculator_stderr = process_result.stderr
    if process_result.returncode != 0:
        add_red_flag(
            result,
            f"calculator returned non-zero exit code for {item_input.product_name}: "
            f"{process_result.returncode}",
        )
        for red_flag in parse_calculator_red_flags(process_result.stdout):
            add_red_flag(result, f"calculator: {red_flag}")
        return False

    fields = parse_calculator_fields(process_result.stdout)
    required_fields = (
        "Status",
        "Input rows count",
        "Cabinet",
        "Cabinet price",
        "Component material total",
        "Work total",
        "Additional materials total",
        "Total preliminary price",
    )
    missing = [field_name for field_name in required_fields if field_name not in fields]
    total = parse_report_integer(fields.get("Total preliminary price", ""))
    row_count = parse_report_integer(fields.get("Input rows count", ""))
    if missing or fields.get("Status") != "PASS" or total is None or row_count is None:
        add_red_flag(
            result,
            f"calculator report is incomplete or failed for {item_input.product_name}",
        )
        return False
    result.item_summaries.append(
        ItemCalculationSummary(
            product_name=item_input.product_name,
            input_rows_count=row_count,
            cabinet=fields["Cabinet"],
            cabinet_price=fields["Cabinet price"],
            component_material_total=fields["Component material total"],
            work_total=fields["Work total"],
            additional_materials_total=fields["Additional materials total"],
            total_preliminary_price=total,
        )
    )
    return True


def execute_profile_position(
    result: CheckedRunResult,
    position: ProfilePositionInput,
    input_csv: Path,
    calculator: ModuleType,
    custom_cabinet_base_cost: int | None,
) -> bool:
    before_count = len(result.item_summaries)
    item_input = ItemCalculatorInput(
        product_name=position.product_name,
        cabinet_code=position.cabinet_code,
        rows=position.rows,
    )
    if not execute_calculator(
        result,
        item_input,
        input_csv,
        custom_cabinet_base_cost=custom_cabinet_base_cost,
    ):
        return False
    if len(result.item_summaries) != before_count + 1:
        add_red_flag(
            result,
            f"missing calculator summary for {position.pricing_position_id}",
        )
        return False
    summary = result.item_summaries[-1]
    cabinet_base = parse_report_integer(summary.cabinet_price)
    material_total = parse_report_integer(summary.component_material_total)
    work_total = parse_report_integer(summary.work_total)
    if (
        cabinet_base is None
        or material_total is None
        or work_total is None
        or summary.input_rows_count != len(position.rows)
    ):
        add_red_flag(
            result,
            f"numeric calculator fields failed for {position.pricing_position_id}",
        )
        return False
    try:
        calculation = calculator.calculate_invoice519_position_price(
            project_id=PRICING_PROFILE_PROJECT_ID,
            profile_decision_id=PRICING_PROFILE_DECISION_ID,
            formula_family=position.formula_family,
            cabinet_code=position.cabinet_code,
            cabinet_base_kzt=cabinet_base,
            additional_cabinet_cost_kzt=position.additional_cabinet_cost_kzt,
            component_material_total_kzt=material_total,
            work_total_kzt=work_total,
            physical_multiplicity=position.physical_multiplicity,
            apartment_count=position.apartment_count,
        )
    except (AttributeError, ValueError):  # fmt: skip
        add_red_flag(
            result,
            f"case formula failed closed for {position.pricing_position_id}",
        )
        return False
    if calculation.cabinet_base_kzt != position.cabinet_base_kzt or (
        position.approved_unit_price_kzt is not None
        and calculation.rounded_unit_price_kzt != position.approved_unit_price_kzt
    ):
        add_red_flag(
            result,
            f"approved formula anchor mismatch at {position.pricing_position_id}",
        )
        return False
    result.position_calculations.append(
        ProfilePositionCalculation(
            pricing_position_id=position.pricing_position_id,
            section=position.section,
            discipline=position.discipline,
            source_document=position.source_document,
            cabinet_group_id=position.cabinet_group_id,
            product_name=position.product_name,
            row_draft_ids=position.row_draft_ids,
            composition_fingerprint_sha256=(position.composition_fingerprint_sha256),
            formula_family=calculation.formula_family,
            cabinet_base_kzt=calculation.cabinet_base_kzt,
            additional_cabinet_cost_kzt=(calculation.additional_cabinet_cost_kzt),
            component_material_total_kzt=(calculation.component_material_total_kzt),
            work_total_kzt=calculation.work_total_kzt,
            apartment_component_kzt=calculation.apartment_component_kzt,
            apartment_count=position.apartment_count,
            unrounded_unit_price_kzt=format(
                calculation.unrounded_unit_price_kzt,
                "f",
            ),
            rounding_stage="AFTER_FULL_UNIT_PRICE_FORMULA",
            rounding_mode="ROUND_HALF_UP",
            rounded_unit_price_kzt=calculation.rounded_unit_price_kzt,
            physical_multiplicity=calculation.physical_multiplicity,
            position_total_kzt=calculation.position_total_kzt,
        )
    )
    result.group_summaries[position.cabinet_group_id] = (
        result.group_summaries.get(position.cabinet_group_id, 0)
        + calculation.position_total_kzt
    )
    return True


def cleanup_temp_csv(result: CheckedRunResult) -> None:
    if not result.temp_csv_paths:
        result.checks["temp cleanup"] = "pass"
        result.temp_csv_deleted = True
        return

    for temp_path in result.temp_csv_paths:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            add_red_flag(
                result,
                f"temporary CSV bridge could not be deleted: {temp_path.name}",
            )
    result.temp_csv_deleted = all(
        not temp_path.exists() for temp_path in result.temp_csv_paths
    )
    result.checks["temp cleanup"] = "pass" if result.temp_csv_deleted else "fail"
    if not result.temp_csv_deleted:
        add_red_flag(result, "temporary CSV bridge still exists after cleanup")


def run_checked_price_calculator_from_completed_draft(
    completed_input_json: Path,
    price_workbook: Path,
    custom_sche_metal_workbook: Path | None = None,
    pricing_profile_path: Path | None = None,
    expected_pricing_profile_sha256: str | None = None,
) -> CheckedRunResult:
    result = CheckedRunResult(
        completed_input_json=resolved(completed_input_json),
        price_workbook=resolved(price_workbook),
    )

    profile_mode = (
        pricing_profile_path is not None or expected_pricing_profile_sha256 is not None
    )
    if profile_mode:
        result.checks.update(
            {
                "pricing profile validation": "fail",
                "initial input SHA": "fail",
                "position inventory": "fail",
                "pre-calculation TOCTOU": "fail",
                "final TOCTOU": "fail",
            }
        )
        if pricing_profile_path is None or expected_pricing_profile_sha256 is None:
            add_red_flag(
                result,
                "pricing profile path and expected SHA are both required",
            )
            return result
        profile = load_pricing_profile(
            result,
            pricing_profile_path,
            expected_pricing_profile_sha256,
        )
        if profile is None or not validate_pricing_profile_contract(profile, result):
            return result
        result.checks["pricing profile validation"] = "pass"
        snapshots = capture_profile_input_shas(
            result,
            profile,
            pricing_profile_path,
            custom_sche_metal_workbook,
            expected_pricing_profile_sha256,
        )
        if snapshots is None:
            return result
        result.checks["initial input SHA"] = "pass"
        result.pricing_profile_provenance = {
            "path": str(resolved(pricing_profile_path)),
            "sha256": expected_pricing_profile_sha256,
            "schema": PRICING_PROFILE_SCHEMA,
            "status": PRICING_PROFILE_STATUS,
            "decision_id": PRICING_PROFILE_DECISION_ID,
            "project_id": PRICING_PROFILE_PROJECT_ID,
        }
        return run_profile_checked_calculation(
            result,
            profile,
            snapshots,
            cast(Path, custom_sche_metal_workbook),
        )

    if not run_completed_input_validation(result):
        return result

    try:
        data = load_completed_input_json(result)
        if data is None:
            return result
        item_inputs = (
            split_v02_item_inputs(data, result)
            if data.get("schema_version") == V02_SCHEMA_VERSION
            else split_item_inputs(data, result)
        )
        if not item_inputs:
            return result
        custom_base_cost: int | None = None
        if any(item.cabinet_code == CUSTOM_SCHE_CABINET_CODE for item in item_inputs):
            if custom_sche_metal_workbook is None:
                result.checks["custom ЩЭ resolver"] = "fail"
                add_red_flag(result, "custom ЩЭ metal workbook is required")
                return result
            try:
                custom_base_cost = resolve_custom_sche_base_cost(
                    custom_sche_metal_workbook
                )
            except (OSError, RuntimeError):  # fmt: skip
                result.checks["custom ЩЭ resolver"] = "fail"
                add_red_flag(result, "custom ЩЭ resolver failed closed")
                return result
        all_bridges_created = True
        all_calculators_passed = True
        for item_input in item_inputs:
            temp_csv = create_csv_bridge(item_input, result)
            if temp_csv is None:
                all_bridges_created = False
                all_calculators_passed = False
                break
            item_custom_base_cost = (
                custom_base_cost
                if item_input.cabinet_code == CUSTOM_SCHE_CABINET_CODE
                else None
            )
            if not execute_calculator(
                result,
                item_input,
                temp_csv,
                custom_cabinet_base_cost=item_custom_base_cost,
            ):
                all_calculators_passed = False
                break
        if all_bridges_created and len(result.temp_csv_paths) == len(item_inputs):
            result.checks["CSV bridge"] = "pass"
        if all_calculators_passed and len(result.item_summaries) == len(item_inputs):
            result.checks["calculator execution"] = "pass"
            result.overall_preliminary_total = sum(
                summary.total_preliminary_price for summary in result.item_summaries
            )
    finally:
        cleanup_temp_csv(result)

    all_checks_pass = all(status == "pass" for status in result.checks.values())
    result.status = "PASS" if all_checks_pass and not result.red_flags else "FAIL"
    return result


def run_profile_checked_calculation(
    result: CheckedRunResult,
    profile: Mapping[str, Any],
    snapshots: Mapping[str, tuple[Path, str]],
    custom_sche_metal_workbook: Path,
) -> CheckedRunResult:
    if not run_completed_input_validation(result):
        return result
    try:
        data = load_completed_input_json(result)
        if data is None:
            return result
        position_inputs = validate_and_build_profile_positions(data, profile, result)
        if not position_inputs:
            return result
        result.checks["position inventory"] = "pass"
        if not recheck_profile_input_shas(
            result,
            snapshots,
            "pre-calculation",
        ):
            return result
        result.checks["pre-calculation TOCTOU"] = "pass"
        try:
            custom_base_cost = resolve_custom_sche_base_cost(custom_sche_metal_workbook)
            calculator = load_calculator_module()
        except (OSError, RuntimeError):  # fmt: skip
            result.checks["custom ЩЭ resolver"] = "fail"
            add_red_flag(result, "profile pricing dependency failed closed")
            return result
        all_calculators_passed = True
        for position in position_inputs:
            item_input = ItemCalculatorInput(
                product_name=position.product_name,
                cabinet_code=position.cabinet_code,
                rows=position.rows,
            )
            temp_csv = create_csv_bridge(item_input, result)
            if temp_csv is None:
                all_calculators_passed = False
                break
            if not execute_profile_position(
                result,
                position,
                temp_csv,
                calculator,
                (
                    custom_base_cost
                    if position.cabinet_code == CUSTOM_SCHE_CABINET_CODE
                    else None
                ),
            ):
                all_calculators_passed = False
                break
        if len(result.temp_csv_paths) == len(position_inputs):
            result.checks["CSV bridge"] = "pass"
        expected_position_count = 55 if has_additive_scope(profile) else 51
        if (
            all_calculators_passed
            and len(result.position_calculations) == expected_position_count
        ):
            result.checks["calculator execution"] = "pass"
            result.overall_preliminary_total = sum(
                calculation.position_total_kzt
                for calculation in result.position_calculations
            )
            result.preliminary_project_total = result.overall_preliminary_total
            metadata = additive_profile_metadata(profile)
            shu_t2_metadata = shu_t2_profile_metadata(profile)
            if shu_t2_metadata is not None:
                target_calculations = [
                    calculation
                    for calculation in result.position_calculations
                    if calculation.pricing_position_id
                    in {
                        "PRICE-POSITION-009",
                        "PRICE-POSITION-023",
                        "PRICE-POSITION-035",
                        "PRICE-POSITION-047",
                    }
                ]
                if (
                    result.overall_preliminary_total != 11963792
                    or len(target_calculations) != 4
                    or [
                        calculation.rounded_unit_price_kzt
                        for calculation in target_calculations
                    ]
                    != [53763, 53763, 53763, 53763]
                    or sum(
                        calculation.position_total_kzt
                        for calculation in target_calculations
                    )
                    != 215052
                ):
                    result.checks["calculator execution"] = "fail"
                    add_red_flag(
                        result,
                        "SHU-T2 RT-820 successor preliminary total contract mismatch",
                    )
            elif metadata is not None and (
                result.overall_preliminary_total
                != metadata.get("candidate_project_total_kzt")
                or [
                    calculation.rounded_unit_price_kzt
                    for calculation in result.position_calculations[-4:]
                ]
                != [53763, 53763, 53763, 53763]
                or sum(
                    calculation.position_total_kzt
                    for calculation in result.position_calculations[-4:]
                )
                != 215052
            ):
                result.checks["calculator execution"] = "fail"
                add_red_flag(
                    result,
                    "ШУ-Т1 successor total/round-before-multiplicity contract mismatch",
                )
        if result.checks["calculator execution"] != "pass":
            return result
        if not recheck_profile_input_shas(result, snapshots, "final"):
            return result
        result.checks["final TOCTOU"] = "pass"
        result.pricing_status = PROFILE_DRAFT_STATUS
        result.approval_status = PROFILE_APPROVAL_STATUS
        result.non_approval_flags = {
            "price_approved": False,
            "invoice_created": False,
            "quote_created": False,
            "client_send_authorized": False,
            "procurement_authorized": False,
            "production_authorized": False,
        }
    finally:
        cleanup_temp_csv(result)
    all_checks_pass = all(status == "pass" for status in result.checks.values())
    result.status = "PASS" if all_checks_pass and not result.red_flags else "FAIL"
    return result


def parse_calculator_summary(stdout: str) -> list[str]:
    lines = stdout.splitlines()
    summary: list[str] = []
    for index, line in enumerate(lines):
        key = line.removesuffix(":")
        if key in CALCULATOR_SUMMARY_KEYS and index + 1 < len(lines):
            value = lines[index + 1]
            if key == "Status":
                summary.append(f"calculator technical status: {value}")
            elif key == "Mode":
                summary.append(f"calculator mode: {value}")
            elif key == "Commercial status":
                summary.append(f"calculator commercial boundary: {value}")
            elif key == "Human Approval":
                summary.append(f"calculator human approval boundary: {value}")
            else:
                summary.append(f"{key}: {value}")
    return summary if summary else ["not available"]


def format_items(values: Sequence[str]) -> list[str]:
    return list(values) if values else ["none"]


def output_or_empty(value: str) -> str:
    return value.rstrip("\r\n") if value else "empty"


def configure_cli_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="strict")


def format_report(result: CheckedRunResult) -> str:
    calculator_summary = parse_calculator_summary(result.calculator_stdout)
    if result.calculator_returncode is not None:
        calculator_summary.insert(
            0,
            f"calculator exit code: {result.calculator_returncode}",
        )
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
    lines.extend(["", "Calculator result:"])
    lines.extend(format_items(calculator_summary))
    if result.calculator_returncode is not None and result.calculator_returncode != 0:
        lines.extend(
            [
                "",
                "Calculator stdout:",
                output_or_empty(result.calculator_stdout),
                "",
                "Calculator stderr:",
                output_or_empty(result.calculator_stderr),
            ]
        )
    lines.extend(["", "Item results:"])
    if result.item_summaries:
        for index, summary in enumerate(result.item_summaries, start=1):
            lines.extend(
                [
                    f"item {index}: {summary.product_name}",
                    f"rows: {summary.input_rows_count}",
                    f"cabinet: {summary.cabinet}",
                    f"cabinet price: {summary.cabinet_price}",
                    f"component materials: {summary.component_material_total}",
                    f"work: {summary.work_total}",
                    f"additional materials: {summary.additional_materials_total}",
                    f"preliminary total: {summary.total_preliminary_price}",
                ]
            )
    else:
        lines.append("not available")
    lines.extend(
        [
            "",
            "Overall preliminary total:",
            (
                f"{result.overall_preliminary_total:,}".replace(",", " ")
                if result.overall_preliminary_total is not None
                else "not calculated"
            ),
        ]
    )
    if result.pricing_status is not None:
        lines.extend(
            [
                "",
                "Pricing result status:",
                result.pricing_status,
                "",
                "Required approval status:",
                result.approval_status or "not available",
                "",
                "Pricing profile provenance:",
                json.dumps(
                    result.pricing_profile_provenance,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "",
                "Exact input SHA provenance:",
                json.dumps(
                    result.input_sha_provenance,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "",
                "Position-level calculations:",
            ]
        )
        lines.extend(
            json.dumps(
                calculation.__dict__,
                ensure_ascii=False,
                sort_keys=True,
            )
            for calculation in result.position_calculations
        )
        lines.extend(
            [
                "",
                "Derived cabinet-group summaries:",
                json.dumps(
                    result.group_summaries,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "",
                "Preliminary project total:",
                str(result.preliminary_project_total),
                "",
                "Explicit non-approval flags:",
                json.dumps(
                    result.non_approval_flags,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ]
        )
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
    configure_cli_utf8()
    args = parse_args(argv)
    result = run_checked_price_calculator_from_completed_draft(
        args.completed_input_json,
        args.price_workbook,
        custom_sche_metal_workbook=args.custom_sche_metal_workbook,
        pricing_profile_path=args.pricing_profile,
        expected_pricing_profile_sha256=args.expected_pricing_profile_sha256,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
