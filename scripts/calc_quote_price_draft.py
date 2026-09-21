"""Calculate a read-only preliminary price draft from confirmed composition CSV."""

from __future__ import annotations

import argparse
import csv
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from openpyxl import load_workbook  # type: ignore[import-untyped]
from price_baseline_contract import (  # type: ignore[import-not-found]
    ACTIVE_VERSION,
    DEFAULT_ACTIVE_SELECTOR,
    HISTORICAL,
    SUCCESSOR,
    mapping_identity_fingerprint,
    require_price_baseline,
    resolve_price_baseline,
)

CSV_DELIMITER = ";"
KRN_SHEET_NAME = "КРН"
FORBIDDEN_PRICE_SHEET_NAME = "Прайс"
MAX_LOOKUP_ROW = 200
REQUIRED_COLUMNS = (
    "product_name",
    "cabinet_code",
    "consumables_factor",
    "component_code",
    "component_qty",
    "install_type",
)
TECHNICAL_COLUMNS = REQUIRED_COLUMNS + ("component_label", "cabinet_label")
SHU_T2_RT820_BINDING_COLUMNS = (
    "technical_successor_contract",
    "technical_successor_sha256",
    "pricing_profile_contract",
    "pricing_profile_sha256",
    "human_decision_sha256",
)
SHU_T2_TECHNICAL_COLUMNS = TECHNICAL_COLUMNS + SHU_T2_RT820_BINDING_COLUMNS
POSITIVE_INTEGER_RE = re.compile(r"[1-9][0-9]*\Z")
POSITIVE_DECIMAL_RE = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
MATERIAL_MULTIPLIER = Decimal("1.25")
FINAL_MULTIPLIER = Decimal("1.15")
INVOICE519_PROJECT_ID = "2024/086"
INVOICE519_PROFILE_DECISION_ID = "IGOR-INVOICE519-PRICING-PROFILE-2024-086-001"
INVOICE519_CASE_CORRECTION = Decimal("1.08765")
INVOICE519_VAT_DIVISOR = Decimal("1.16")
INVOICE519_BUYER_REPRESENTATIVE_BONUS = Decimal("1.2")
INVOICE519_INTERNAL_MATERIAL_FACTOR = Decimal("1.2")
INVOICE519_SCHE_APARTMENT_COMPONENT_KZT = 5100
INVOICE519_MODULAR_FORMULA_FAMILY = "CURRENT_MODULAR_CASE_PROFILE"
INVOICE519_SCHE_FORMULA_FAMILY = "CURRENT_SCHE_CASE_PROFILE"
INVOICE519_SCHE_CABINET_CODE = "CAB-SCHE-BI-900X900X120-M12"
INVOICE519_CABINET_BASES_KZT = {
    "CAB-KURN-038-24": 12557,
    "CAB-KRN-18": 7678,
    "CAB-KRN-12": 6936,
    "CAB-KRN-24": 7985,
    "CAB-SCHE-BI-900X900X120-M12": 20305,
}


@dataclass(frozen=True)
class ComponentDefinition:
    workbook_label: str | None
    install_type: str


COMPONENT_DEFINITIONS = {
    "EKF-VA47-29-1P": ComponentDefinition(
        workbook_label="ВА47 1 полюсный",
        install_type="modular_1p",
    ),
    "EKF-VA47-29-2P": ComponentDefinition(
        workbook_label="ВА47 2 полюсный",
        install_type="modular_2p",
    ),
    "EKF-VA47-29-3P": ComponentDefinition(
        workbook_label="ВА47 3 полюсный до 63А",
        install_type="modular_3p",
    ),
    "EKF-VN-32-1P": ComponentDefinition(
        workbook_label="ВН-32 1Р 16-25-40-63А",
        install_type="load_switch_1p",
    ),
    "EKF-VN-32-2P": ComponentDefinition(
        workbook_label="ВН-32 2Р 16-25-40-63А",
        install_type="load_switch_2p",
    ),
    "EKF-VN-32-3P": ComponentDefinition(
        workbook_label="ВН-32 3Р 16-25-40-63-80-100А",
        install_type="load_switch_3p",
    ),
    "EKF-AD32-1P-N": ComponentDefinition(
        workbook_label="УЗО АД-32 1Р+N до 63А EKF",
        install_type="diff_1p_n",
    ),
    "EKF-AD12-1P-N-C16-30MA-4P5KA": ComponentDefinition(
        workbook_label=None,
        install_type="diff_1p_n",
    ),
    "EKF-RN-47": ComponentDefinition(
        workbook_label="независимый расцепитель для ВА47 РН47",
        install_type="modular_1p",
    ),
}
CABINET_DEFINITIONS = {
    "CAB-KURN-038-24": "Корпус КУРН-0,38-24 540х490х170",
    "CAB-KRN-18": "Корпус КРН-18 265х440х100",
    "CAB-KRN-12": "Корпус КРН-12 265х330х100",
    "CAB-KRN-24": "Корпус КРН-24 395х330х100",
    "CAB-SCHE-BI-900X900X120-M12": ("Встроенный ЩЭ, 900×900×120 мм, металл 1.2 мм"),
}
CABINET_TECHNICAL_LABELS = {
    "CAB-KURN-038-24": "Корпус КУРН-0,38-24 540×490×170 мм, металл",
    "CAB-KRN-18": "Корпус КРН-18 265×440×100 мм, металл",
    "CAB-KRN-12": "Корпус КРН-12 265×330×100 мм, металл",
    "CAB-KRN-24": "Корпус КРН-24 395×330×100 мм, металл",
    "CAB-SCHE-BI-900X900X120-M12": ("Встроенный ЩЭ, 900×900×120 мм, металл 1.2 мм"),
}
CABINET_SOURCE_TEMPLATE_CODES = {
    "ПР": "CAB-KURN-038-24",
    "Щоф": "CAB-KRN-18",
    "ШУ-Т2": "CAB-KRN-12",
    "ЩАО-1Ж": "CAB-KRN-12",
    "ЩАО-2Ж": "CAB-KRN-12",
    "ЩАО-3Ж": "CAB-KRN-12",
    "ЩО-1Ж": "CAB-KRN-12",
    "ЩО-2Ж": "CAB-KRN-12",
    "ЩО-3Ж": "CAB-KRN-12",
    "ЩС": "CAB-KRN-24",
}
UNRESOLVED_COMPONENT_MAPPING_REQUESTS: dict[str, str] = {}
PRICING_DECISION_ARTIFACT_SHA256 = (
    "777faed80c8ef92782378dd2a788160af8ad2252d8cb4f539560f15657a1d96e"
)
AD12_PRICE_MAPPING_DECISION_ARTIFACT_SHA256 = (
    "f67c0d79ec404a739ad5bdc3650a6259b9dc496a6f23ebffb7f29e7a9a24a17a"
)
AD12_PRICE_MAPPING_DECISION_ARTIFACT_SCHEMA = (
    "technical_ad12_price_mapping_human_decisions.v0.1"
)
AD12_PRICE_MAPPING_DECISION_ARTIFACT_STATUS = (
    "IGOR_AD12_SHARED_PRICE_MAPPING_APPROVED_NOT_APPLIED"
)
AD12_PRICE_MAPPING_DECISION_ID = "IGOR-AD12-SHARED-PRICE-MAPPING-2024-086-001"
RESOLVED_COMPONENT_MAPPING_PROVENANCE = {
    "COMPONENT-MAPPING-005": {
        "article": "D63N46ES16C100",
        "component_code": "EKF-AVDT63N-3P-N-C16-100MA-6KA-S",
        "pricing_decision_artifact_sha256": PRICING_DECISION_ARTIFACT_SHA256,
    },
    "COMPONENT-MAPPING-012": {
        "article": "DA32-6-16-30-ac-pro",
        "component_code": "EKF-AD32-1P-N",
        "pricing_decision_artifact_sha256": PRICING_DECISION_ARTIFACT_SHA256,
    },
    "COMPONENT-MAPPING-009": {
        "article": "DA12-16-30-bas",
        "component_code": "EKF-AD12-1P-N-C16-30MA-4P5KA",
        "row_draft_ids": (
            "ROW-DRAFT-0024",
            "ROW-DRAFT-0025",
            "ROW-DRAFT-0026",
            "ROW-DRAFT-0027",
        ),
        "human_decision_artifact_sha256": (
            "5d6e0de7af052c959abff015f41081c8bddc10e834fe4f971e8a7d2e60f19c46"
        ),
        "pricing_decision_artifact_sha256": (
            AD12_PRICE_MAPPING_DECISION_ARTIFACT_SHA256
        ),
        "pricing_decision_artifact_schema": (
            AD12_PRICE_MAPPING_DECISION_ARTIFACT_SCHEMA
        ),
        "pricing_decision_artifact_status": (
            AD12_PRICE_MAPPING_DECISION_ARTIFACT_STATUS
        ),
        "pricing_decision_id": AD12_PRICE_MAPPING_DECISION_ID,
        "direct_human_shared_price_decision": True,
        "ad32_fallback_used_for_ad12": False,
        "scope_expansion": False,
    },
    "COMPONENT-MAPPING-016": {
        "article": "DA12-16-30-bas",
        "component_code": "EKF-AD12-1P-N-C16-30MA-4P5KA",
        "row_draft_ids": (
            "ROW-DRAFT-0074",
            "ROW-DRAFT-0075",
        ),
        "human_decision_artifact_sha256": (
            "5d6e0de7af052c959abff015f41081c8bddc10e834fe4f971e8a7d2e60f19c46"
        ),
        "pricing_decision_artifact_sha256": (
            AD12_PRICE_MAPPING_DECISION_ARTIFACT_SHA256
        ),
        "pricing_decision_artifact_schema": (
            AD12_PRICE_MAPPING_DECISION_ARTIFACT_SCHEMA
        ),
        "pricing_decision_artifact_status": (
            AD12_PRICE_MAPPING_DECISION_ARTIFACT_STATUS
        ),
        "pricing_decision_id": AD12_PRICE_MAPPING_DECISION_ID,
        "direct_human_shared_price_decision": True,
        "ad32_fallback_used_for_ad12": False,
        "scope_expansion": False,
    },
}
APPROVED_MAPPING_005_SOURCE_LABELS = ("АВДТ-34, 4P, C16, 100мА",)


@dataclass(frozen=True)
class TechnicalSignature:
    apparatus_category: str
    poles: int
    rating_a: int
    residual_current_ma: int | None
    trip_curve: str | None
    install_type: str
    breaking_capacity_ka: Decimal | None = None


@dataclass(frozen=True)
class ApprovedComponentPriceMapping:
    signature: TechnicalSignature
    sheet_name: str
    row: int
    expected_label: str
    expected_material_price: int
    expected_work_price: int
    component_code: str | None = None
    strict_raw_label: bool = False
    mapping_id: str = ""


@dataclass(frozen=True)
class CabinetSignature:
    cabinet_code: str
    width_mm: int
    height_mm: int
    depth_mm: int
    material: str


@dataclass(frozen=True)
class ApprovedCabinetPriceMapping:
    signature: CabinetSignature
    sheet_name: str
    row: int
    expected_label: str
    expected_price: int
    mapping_id: str = ""


APPROVED_COMPONENT_PRICE_MAPPINGS = (
    ApprovedComponentPriceMapping(
        TechnicalSignature("mccb", 3, 63, None, None, "mccb_up_to_100a"),
        "ЩР",
        8,
        "ВА55/57/59, АМ1 3 полюсные от 16 до 63А",
        13000,
        1800,
        mapping_id="COMPONENT-PRICE-MCCB-3P-63A",
    ),
    ApprovedComponentPriceMapping(
        TechnicalSignature("rcbo", 2, 16, 30, "C", "diff_1p_n"),
        "КРН",
        5,
        "УЗО АД-32 1Р+N до 63А EKF",
        4100,
        432,
        mapping_id="COMPONENT-PRICE-RCBO-2P-C16-30MA",
    ),
    ApprovedComponentPriceMapping(
        TechnicalSignature("rcbo", 2, 20, 30, "C", "diff_1p_n"),
        "КРН",
        5,
        "УЗО АД-32 1Р+N до 63А EKF",
        4100,
        432,
        mapping_id="COMPONENT-PRICE-RCBO-2P-C20-30MA",
    ),
    ApprovedComponentPriceMapping(
        TechnicalSignature("load_switch", 3, 32, None, None, "load_switch_3p"),
        "КРН",
        14,
        "ВН-32 3Р 16-25-40-63-80-100А",
        2750,
        540,
        mapping_id="COMPONENT-PRICE-LOAD-SWITCH-3P-32A",
    ),
    ApprovedComponentPriceMapping(
        TechnicalSignature(
            "rcbo",
            2,
            16,
            30,
            "C",
            "diff_1p_n",
            Decimal("6"),
        ),
        "КРН",
        5,
        "УЗО АД-32 1Р+N до 63А EKF",
        4100,
        432,
        component_code="EKF-AD32-1P-N",
        strict_raw_label=True,
        mapping_id="COMPONENT-MAPPING-012",
    ),
    ApprovedComponentPriceMapping(
        TechnicalSignature(
            "rcbo",
            2,
            16,
            30,
            "C",
            "diff_1p_n",
            Decimal("4.5"),
        ),
        "КРН",
        5,
        "УЗО АД-32 1Р+N до 63А EKF",
        4100,
        432,
        component_code="EKF-AD12-1P-N-C16-30MA-4P5KA",
        strict_raw_label=True,
        mapping_id="COMPONENT-MAPPING-009-016",
    ),
    ApprovedComponentPriceMapping(
        TechnicalSignature("rcbo", 4, 16, 100, "C", "diff_3p_4p"),
        "КРН",
        28,
        "УЗО АД-32 1Р+N до 63А 100мА-300мА EKF ",
        8000,
        432,
        component_code="EKF-AVDT63N-3P-N-C16-100MA-6KA-S",
        strict_raw_label=True,
        mapping_id="COMPONENT-MAPPING-005",
    ),
    ApprovedComponentPriceMapping(
        TechnicalSignature(
            "rcbo",
            4,
            16,
            100,
            "C",
            "diff_3p_4p",
            Decimal("6"),
        ),
        "КРН",
        28,
        "УЗО АД-32 1Р+N до 63А 100мА-300мА EKF ",
        8000,
        432,
        component_code="EKF-AVDT63N-3P-N-C16-100MA-6KA-S",
        strict_raw_label=True,
        mapping_id="COMPONENT-MAPPING-005-6KA",
    ),
    ApprovedComponentPriceMapping(
        TechnicalSignature(
            "temperature_relay",
            0,
            0,
            None,
            None,
            "temperature_relay_din_2mod",
        ),
        "КРН",
        19,
        "Терморегулятор RT-820",
        15000,
        900,
        component_code="EKF-RT-820",
        strict_raw_label=True,
        mapping_id="COMPONENT-PRICE-RT820",
    ),
)
RT820_COMPONENT_CODE = "EKF-RT-820"
RT820_PRODUCT_NAME = "ШУ-Т1"
RT820_SHU_T2_PRODUCT_NAME = "ШУ-Т2"
RT820_INSTALL_TYPE = "temperature_relay_din_2mod"
RT820_COMPONENT_LABEL = "Реле температуры RT-820 EKF PROxima с внешним датчиком"
RT820_CABINET_CODE = "CAB-KRN-12"
RT820_APPROVED_MAPPING = APPROVED_COMPONENT_PRICE_MAPPINGS[-1]
SUCCESSOR_COMPONENT_PRICE_MAPPINGS = tuple(
    (
        replace(
            mapping,
            expected_material_price=(
                15000 if mapping.sheet_name == "ЩР" and mapping.row == 8 else 4500
            ),
        )
        if (mapping.sheet_name, mapping.row) in {("ЩР", 8), ("КРН", 5)}
        else mapping
    )
    for mapping in APPROVED_COMPONENT_PRICE_MAPPINGS
)


def component_mapping_identity(
    mapping: ApprovedComponentPriceMapping,
) -> dict[str, Any]:
    signature = mapping.signature
    return {
        "authority": "TECHNICAL_MAPPING_IDENTITY",
        "mapping_id": mapping.mapping_id,
        "apparatus_category": signature.apparatus_category,
        "poles": signature.poles,
        "rating_a": signature.rating_a,
        "residual_current_ma": signature.residual_current_ma,
        "trip_curve": signature.trip_curve,
        "install_type": signature.install_type,
        "breaking_capacity_ka": (
            str(signature.breaking_capacity_ka)
            if signature.breaking_capacity_ka is not None
            else None
        ),
        "component_code": mapping.component_code,
        "sheet": mapping.sheet_name,
        "row": mapping.row,
        "expected_label": mapping.expected_label,
        "strict_label": mapping.strict_raw_label,
    }


def cabinet_mapping_identity(mapping: ApprovedCabinetPriceMapping) -> dict[str, Any]:
    signature = mapping.signature
    return {
        "authority": "TECHNICAL_MAPPING_IDENTITY",
        "mapping_id": mapping.mapping_id,
        "cabinet_code": signature.cabinet_code,
        "width_mm": signature.width_mm,
        "height_mm": signature.height_mm,
        "depth_mm": signature.depth_mm,
        "material": signature.material,
        "sheet": mapping.sheet_name,
        "row": mapping.row,
        "expected_label": mapping.expected_label,
        "strict_label": False,
    }


def _snapshot_by_id(
    snapshot: Sequence[Mapping[str, Any]], kind: str
) -> dict[str, Mapping[str, Any]]:
    return {
        str(entry["mapping_id"]): entry
        for entry in snapshot
        if entry.get("mapping_kind") == kind
    }


def active_component_price_mappings(
    snapshot: Sequence[Mapping[str, Any]],
) -> tuple[ApprovedComponentPriceMapping, ...]:
    by_id = _snapshot_by_id(snapshot, "component_exact")
    resolved: list[ApprovedComponentPriceMapping] = []
    for mapping in APPROVED_COMPONENT_PRICE_MAPPINGS:
        entry = by_id.get(mapping.mapping_id)
        if entry is None:
            raise ValueError(f"active manifest missing mapping {mapping.mapping_id}")
        identity = cast(Mapping[str, Any], entry["identity"])
        if mapping_identity_fingerprint(component_mapping_identity(mapping)) != entry[
            "identity_fingerprint"
        ] or dict(identity) != component_mapping_identity(mapping):
            raise ValueError(
                f"active manifest mapping identity drift: {mapping.mapping_id}"
            )
        prices = cast(Mapping[str, Any], entry["prices"])
        resolved.append(
            replace(
                mapping,
                expected_material_price=cast(int, prices["material_kzt"]),
                expected_work_price=cast(int, prices["work_kzt"]),
            )
        )
    return tuple(resolved)


def active_cabinet_price_mappings(
    snapshot: Sequence[Mapping[str, Any]],
) -> tuple[ApprovedCabinetPriceMapping, ...]:
    by_id = _snapshot_by_id(snapshot, "cabinet_exact")
    resolved: list[ApprovedCabinetPriceMapping] = []
    for mapping in APPROVED_CABINET_PRICE_MAPPINGS:
        entry = by_id.get(mapping.mapping_id)
        if entry is None:
            raise ValueError(f"active manifest missing mapping {mapping.mapping_id}")
        identity = cast(Mapping[str, Any], entry["identity"])
        if mapping_identity_fingerprint(cabinet_mapping_identity(mapping)) != entry[
            "identity_fingerprint"
        ] or dict(identity) != cabinet_mapping_identity(mapping):
            raise ValueError(
                f"active manifest mapping identity drift: {mapping.mapping_id}"
            )
        prices = cast(Mapping[str, Any], entry["prices"])
        resolved.append(replace(mapping, expected_price=cast(int, prices["price_kzt"])))
    return tuple(resolved)


def component_price_mappings(
    version: str,
    snapshot: Sequence[Mapping[str, Any]] = (),
) -> tuple[ApprovedComponentPriceMapping, ...]:
    if version == HISTORICAL.version:
        return APPROVED_COMPONENT_PRICE_MAPPINGS
    if version == SUCCESSOR.version:
        return SUCCESSOR_COMPONENT_PRICE_MAPPINGS
    if version == ACTIVE_VERSION:
        return active_component_price_mappings(snapshot)
    raise ValueError("unknown price baseline version")


SHU_T2_RT820_TECHNICAL_CONTRACT = "controlled_shu_t2_rt820_technical_successor.v0.1"
SHU_T2_RT820_TECHNICAL_SHA256 = (
    "c27c2c3032699cb07c981aeb4af429b27ec18180225319f45ce65ab77fedee44"
)
SHU_T2_RT820_PROFILE_CONTRACT = "controlled_shu_t2_rt820_pricing_profile_successor.v0.1"
SHU_T2_RT820_PROFILE_SHA256 = (
    "ae604108514a2b19b58c262c0e2fae379be6eac8a7286ffc2da605ac29637c9e"
)
SHU_T2_RT820_HUMAN_DECISION_SHA256 = (
    "92a79401591fa6202af493848dd979a227ae20da8e66b8dea6e8084fc80c2ac6"
)

APPROVED_CABINET_PRICE_MAPPINGS = (
    ApprovedCabinetPriceMapping(
        CabinetSignature("ПР", 800, 600, 250, "metal"),
        "ЩР",
        8,
        "800х600х250",
        21336,
        mapping_id="CABINET-PRICE-PR-800X600X250",
    ),
    ApprovedCabinetPriceMapping(
        CabinetSignature("КРН-36", 540, 330, 100, "metal"),
        "КРН",
        9,
        "Корпус КРН-36 540х330х100",
        9405,
        mapping_id="CABINET-PRICE-KRN-36",
    ),
)


@dataclass(frozen=True)
class CompositionRow:
    product_name: str
    cabinet_code: str
    consumables_factor: Decimal
    component_code: str
    component_qty: int
    install_type: str
    component_label: str | None = None
    cabinet_label: str | None = None
    component_mapping: ApprovedComponentPriceMapping | None = None
    cabinet_mapping: ApprovedCabinetPriceMapping | None = None
    technical_mapping_validated: bool = False


@dataclass
class PriceCalculationResult:
    price_workbook: Path
    input_csv: Path
    price_baseline_version: str = HISTORICAL.version
    price_baseline_sha256: str | None = None
    price_baseline_manifest_id: str | None = None
    price_baseline_manifest_sha256: str | None = None
    price_mapping_snapshot: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    active_selector_path: Path | None = None
    status: str = "FAIL"
    product_name: str | None = None
    input_rows_count: int = 0
    cabinet_code: str | None = None
    cabinet_label: str | None = None
    cabinet_price: int | None = None
    component_material_total: int | None = None
    work_total: int | None = None
    additional_materials_total: Decimal | None = None
    consumables_factor: Decimal | None = None
    base: Decimal | None = None
    total_preliminary_price: int | None = None
    red_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Invoice519PositionPrice:
    formula_family: str
    cabinet_base_kzt: int
    additional_cabinet_cost_kzt: int
    component_material_total_kzt: int
    work_total_kzt: int
    apartment_component_kzt: int
    unrounded_unit_price_kzt: Decimal
    rounded_unit_price_kzt: int
    physical_multiplicity: int
    position_total_kzt: int


def calculate_invoice519_position_price(
    *,
    project_id: str,
    profile_decision_id: str,
    formula_family: str,
    cabinet_code: str,
    cabinet_base_kzt: int,
    additional_cabinet_cost_kzt: int,
    component_material_total_kzt: int,
    work_total_kzt: int,
    physical_multiplicity: int,
    apartment_count: int | None = None,
) -> Invoice519PositionPrice:
    """Apply the exact case-scoped Invoice 519 position formula."""
    if (
        project_id != INVOICE519_PROJECT_ID
        or profile_decision_id != INVOICE519_PROFILE_DECISION_ID
    ):
        raise ValueError("Invoice 519 pricing tail is restricted to its exact project")
    expected_base = INVOICE519_CABINET_BASES_KZT.get(cabinet_code)
    if expected_base is None or cabinet_base_kzt != expected_base:
        raise ValueError("cabinet base does not match the exact Invoice 519 profile")
    if (
        additional_cabinet_cost_kzt != 0
        or component_material_total_kzt < 0
        or work_total_kzt < 0
        or physical_multiplicity <= 0
    ):
        raise ValueError("Invoice 519 position inputs are outside the approved scope")

    apartment_component_kzt = 0
    if formula_family == INVOICE519_SCHE_FORMULA_FAMILY:
        if cabinet_code != INVOICE519_SCHE_CABINET_CODE or apartment_count not in {
            3,
            4,
            5,
            6,
        }:
            raise ValueError("custom ЩЭ formula identity is invalid")
        apartment_component_kzt = (
            INVOICE519_SCHE_APARTMENT_COMPONENT_KZT * apartment_count
        )
    elif formula_family == INVOICE519_MODULAR_FORMULA_FAMILY:
        if cabinet_code == INVOICE519_SCHE_CABINET_CODE or apartment_count is not None:
            raise ValueError("modular formula cannot use custom ЩЭ inputs")
    else:
        raise ValueError("reserved or unknown formula family cannot be applied")

    formula_base = (
        Decimal(cabinet_base_kzt)
        + Decimal(additional_cabinet_cost_kzt)
        + Decimal(component_material_total_kzt) * INVOICE519_INTERNAL_MATERIAL_FACTOR
        + Decimal(work_total_kzt)
        + Decimal(apartment_component_kzt)
    )
    unrounded = (
        formula_base
        * MATERIAL_MULTIPLIER
        * FINAL_MULTIPLIER
        * INVOICE519_CASE_CORRECTION
        / INVOICE519_VAT_DIVISOR
        * INVOICE519_BUYER_REPRESENTATIVE_BONUS
    )
    rounded = int(unrounded.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return Invoice519PositionPrice(
        formula_family=formula_family,
        cabinet_base_kzt=cabinet_base_kzt,
        additional_cabinet_cost_kzt=additional_cabinet_cost_kzt,
        component_material_total_kzt=component_material_total_kzt,
        work_total_kzt=work_total_kzt,
        apartment_component_kzt=apartment_component_kzt,
        unrounded_unit_price_kzt=unrounded,
        rounded_unit_price_kzt=rounded,
        physical_multiplicity=physical_multiplicity,
        position_total_kzt=rounded * physical_multiplicity,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate a read-only preliminary price draft from confirmed "
            "composition CSV using approved worksheet mappings."
        )
    )
    parser.add_argument(
        "--price-workbook",
        type=Path,
        help="Exact workbook path; omit to resolve the active approved manifest",
    )
    parser.add_argument(
        "--price-baseline-version",
        help="Explicit frozen/released binding; omit for active approved baseline",
    )
    parser.add_argument(
        "--active-selector",
        type=Path,
        default=DEFAULT_ACTIVE_SELECTOR,
        help="Active selector path for future/non-profile calculations",
    )
    parser.add_argument(
        "--input-csv",
        required=True,
        type=Path,
        help="Path to confirmed semicolon-delimited composition CSV",
    )
    parser.add_argument(
        "--custom-cabinet-base-cost",
        type=int,
        help=("Checked positive integer base cost for CAB-SCHE-BI-900X900X120-M12"),
    )
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def add_red_flag(result: PriceCalculationResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def parse_positive_decimal(value: str) -> Decimal | None:
    if POSITIVE_DECIMAL_RE.fullmatch(value) is None:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    if parsed <= 0:
        return None
    return parsed


def parse_breaking_capacity_ka(component_label: str) -> Decimal | None:
    normalized = normalize_workbook_label(component_label)
    if normalized is None:
        return None
    match = re.search(
        r"\b(\d+(?:[.,]\d+)?)\s*[kк]\s*[aа]\b",
        normalized.casefold(),
    )
    return Decimal(match.group(1).replace(",", ".")) if match is not None else None


def parse_nominal_current_a(component_label: str) -> int | None:
    folded = component_label.casefold()
    patterns = (
        r"\b(?:i|и)[рpн]\s*=\s*(\d+)\s*[aа]\b",
        r"\b\d+\s*/\s*(\d+)\s*[aа]\b",
        r"\bc\s*(\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, folded)
        if match is not None:
            return int(match.group(1))
    matches = re.findall(r"\b(\d+)\s*[aа]\b", folded)
    return int(matches[-1]) if matches else None


def parse_component_signature(
    component_label: str,
    install_type: str,
) -> TechnicalSignature | None:
    normalized = normalize_workbook_label(component_label)
    if normalized is None:
        return None
    folded = normalized.casefold()
    poles_match = re.search(r"\b([1-4])\s*[pр]\b", folded)
    if poles_match is None:
        return None
    poles = int(poles_match.group(1))
    breaking_capacity = parse_breaking_capacity_ka(normalized)

    if install_type in {"modular_1p", "modular_2p", "modular_3p"} and (
        "автоматический выключатель" in folded or "выключатель автоматический" in folded
    ):
        expected_poles = int(install_type.removeprefix("modular_").removesuffix("p"))
        if poles != expected_poles or breaking_capacity is None:
            return None
        category = "mcb"
        rating = parse_nominal_current_a(normalized)
        rating_match = re.match(r"(\d+)", str(rating)) if rating is not None else None
        curve = "C" if re.search(r"(?:\(|\b)(?:c|с)(?=\d|\)|\b)", folded) else None
        if curve is None:
            return None
        residual_current = None
    elif install_type == "mccb_up_to_100a" and "автоматический выключатель" in folded:
        category = "mccb"
        rating_match = re.search(r"\b(\d+)\s*а\b", folded)
        curve = None
        residual_current = None
    elif install_type == "diff_1p_n" and ("авдт" in folded or "ад12" in folded):
        category = "rcbo"
        rating = parse_nominal_current_a(normalized)
        rating_match = re.match(r"(\d+)", str(rating)) if rating is not None else None
        residual_match = re.search(r"(?:/|,)\s*(\d+)\s*ма\b", folded)
        if (
            residual_match is None
            or re.search(r"(?:\b|\()(?:c|с)(?=\d|\)|\b)", folded) is None
        ):
            return None
        curve = "C"
        residual_current = int(residual_match.group(1))
    elif install_type == "diff_3p_4p" and any(
        normalized.startswith(label) for label in APPROVED_MAPPING_005_SOURCE_LABELS
    ):
        category = "rcbo"
        rating_match = re.search(r"\bc\s*(\d+)\b", folded)
        residual_match = re.search(r",\s*(\d+)\s*ма\b", folded)
        if residual_match is None:
            return None
        curve = "C"
        residual_current = int(residual_match.group(1))
    elif install_type == "load_switch_3p" and "выключатель нагрузки" in folded:
        category = "load_switch"
        rating_match = re.search(r"\b(\d+)\s*а\b", folded)
        curve = None
        residual_current = None
    else:
        return None

    if rating_match is None:
        return None
    return TechnicalSignature(
        apparatus_category=category,
        poles=poles,
        rating_a=int(rating_match.group(1)),
        residual_current_ma=residual_current,
        trip_curve=curve,
        install_type=install_type,
        breaking_capacity_ka=breaking_capacity,
    )


def technical_component_definition_matches(
    signature: TechnicalSignature | None,
    component_code: str,
    install_type: str,
) -> bool:
    definition = COMPONENT_DEFINITIONS.get(component_code)
    if (
        signature is None
        or definition is None
        or definition.install_type != install_type
        or signature.install_type != install_type
    ):
        return False
    if install_type.startswith("modular_"):
        expected_poles = {
            "EKF-VA47-29-1P": 1,
            "EKF-VA47-29-2P": 2,
            "EKF-VA47-29-3P": 3,
        }.get(component_code)
        return (
            signature.apparatus_category == "mcb"
            and signature.poles == expected_poles
            and signature.trip_curve == "C"
            and signature.breaking_capacity_ka is not None
        )
    if component_code == "EKF-AD12-1P-N-C16-30MA-4P5KA":
        return signature == TechnicalSignature(
            "rcbo",
            2,
            16,
            30,
            "C",
            "diff_1p_n",
            Decimal("4.5"),
        )
    return False


def exact_component_price_mapping_required(component_code: str | None) -> bool:
    return any(
        mapping.component_code == component_code
        for mapping in APPROVED_COMPONENT_PRICE_MAPPINGS
        if mapping.component_code is not None
    )


def technical_cabinet_definition_matches(
    cabinet_code: str,
    cabinet_label: str,
) -> bool:
    expected = CABINET_TECHNICAL_LABELS.get(cabinet_code)
    if expected is None:
        return False
    return (
        normalize_workbook_label(cabinet_label) == normalize_workbook_label(expected)
        and parse_cabinet_signature(cabinet_code, cabinet_label) is not None
    )


def parse_cabinet_signature(
    cabinet_code: str,
    cabinet_label: str,
) -> CabinetSignature | None:
    normalized = normalize_workbook_label(cabinet_label)
    if normalized is None:
        return None
    dimensions = re.search(
        r"(\d+)\s*[xх×*]\s*(\d+)\s*[xх×*]\s*(\d+)",
        normalized.casefold(),
    )
    if dimensions is None or "металл" not in normalized.casefold():
        return None
    return CabinetSignature(
        cabinet_code=normalize_workbook_label(cabinet_code) or cabinet_code,
        width_mm=int(dimensions.group(1)),
        height_mm=int(dimensions.group(2)),
        depth_mm=int(dimensions.group(3)),
        material="metal",
    )


def resolve_component_mapping(
    signature: TechnicalSignature,
    component_code: str | None = None,
    mappings: tuple[ApprovedComponentPriceMapping, ...] | None = None,
) -> ApprovedComponentPriceMapping | None:
    exact_mapping_required = exact_component_price_mapping_required(component_code)
    matches = [
        mapping
        for mapping in (
            APPROVED_COMPONENT_PRICE_MAPPINGS if mappings is None else mappings
        )
        if mapping.signature == signature
        and (
            mapping.component_code == component_code
            if exact_mapping_required
            else mapping.component_code is None
            or mapping.component_code == component_code
        )
    ]
    return matches[0] if len(matches) == 1 else None


def resolve_case_scoped_rt820_mapping(
    row: Mapping[str, str],
) -> ApprovedComponentPriceMapping | None:
    """Resolve RT-820 only for one of the two exact project contracts."""
    if row.get("component_code") != RT820_COMPONENT_CODE:
        return None
    legacy_shu_t1 = (
        row.get("product_name") == RT820_PRODUCT_NAME
        and row.get("cabinet_code") == RT820_CABINET_CODE
        and row.get("install_type") == RT820_INSTALL_TYPE
        and row.get("component_label") == RT820_COMPONENT_LABEL
    )
    exact_shu_t2 = (
        row.get("product_name") == RT820_SHU_T2_PRODUCT_NAME
        and row.get("cabinet_code") == RT820_CABINET_CODE
        and row.get("install_type") == RT820_INSTALL_TYPE
        and row.get("component_label") == RT820_COMPONENT_LABEL
        and row.get("technical_successor_contract") == SHU_T2_RT820_TECHNICAL_CONTRACT
        and row.get("technical_successor_sha256") == SHU_T2_RT820_TECHNICAL_SHA256
        and row.get("pricing_profile_contract") == SHU_T2_RT820_PROFILE_CONTRACT
        and row.get("pricing_profile_sha256") == SHU_T2_RT820_PROFILE_SHA256
        and row.get("human_decision_sha256") == SHU_T2_RT820_HUMAN_DECISION_SHA256
    )
    if legacy_shu_t1 or exact_shu_t2:
        return RT820_APPROVED_MAPPING
    return None


def signature_requires_component_code(signature: TechnicalSignature) -> bool:
    return any(
        mapping.signature == signature and mapping.component_code is not None
        for mapping in APPROVED_COMPONENT_PRICE_MAPPINGS
    )


def resolve_cabinet_mapping(
    signature: CabinetSignature,
    mappings: tuple[ApprovedCabinetPriceMapping, ...] | None = None,
) -> ApprovedCabinetPriceMapping | None:
    matches = [
        mapping
        for mapping in (
            APPROVED_CABINET_PRICE_MAPPINGS if mappings is None else mappings
        )
        if mapping.signature == signature
    ]
    return matches[0] if len(matches) == 1 else None


def load_composition_rows(result: PriceCalculationResult) -> list[CompositionRow]:
    try:
        selected_mappings = component_price_mappings(
            result.price_baseline_version,
            result.price_mapping_snapshot,
        )
        selected_cabinet_mappings = (
            active_cabinet_price_mappings(result.price_mapping_snapshot)
            if result.price_baseline_version == ACTIVE_VERSION
            else APPROVED_CABINET_PRICE_MAPPINGS
        )
    except ValueError as exc:
        add_red_flag(result, str(exc))
        return []
    path = result.input_csv
    if not path.is_file():
        add_red_flag(result, f"input CSV does not exist: {path}")
        return []
    if path.suffix.casefold() != ".csv":
        add_red_flag(result, "input composition suffix must be .csv")
        return []

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.reader(csv_file, delimiter=CSV_DELIMITER, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                add_red_flag(result, "input composition CSV is empty")
                return []
            raw_rows = list(reader)
    except UnicodeDecodeError:
        add_red_flag(result, "input composition CSV must be valid UTF-8")
        return []
    except csv.Error:
        add_red_flag(result, "input composition CSV is invalid")
        return []
    except OSError:
        add_red_flag(result, "input composition CSV could not be read")
        return []

    result.input_rows_count = len(raw_rows)
    header_tuple = tuple(header)
    if header_tuple not in (
        REQUIRED_COLUMNS,
        TECHNICAL_COLUMNS,
        SHU_T2_TECHNICAL_COLUMNS,
    ):
        add_red_flag(
            result,
            "input header must exactly match a supported composition contract",
        )
        return []
    if not raw_rows:
        add_red_flag(result, "input composition CSV must contain at least one row")
        return []

    rows: list[CompositionRow] = []
    for row_number, values in enumerate(raw_rows, start=2):
        if len(values) != len(header_tuple):
            add_red_flag(result, f"row {row_number}: field count mismatch")
            continue

        row = dict(zip(header_tuple, values, strict=True))
        empty_columns = [column for column in header_tuple if row[column].strip() == ""]
        if empty_columns:
            add_red_flag(
                result,
                f"row {row_number}: required fields are empty: "
                f"{', '.join(empty_columns)}",
            )
            continue

        factor = parse_positive_decimal(row["consumables_factor"])
        if factor is None:
            add_red_flag(
                result,
                f"row {row_number}: consumables_factor must be a positive "
                "dot-decimal number",
            )
            continue

        quantity_text = row["component_qty"]
        if POSITIVE_INTEGER_RE.fullmatch(quantity_text) is None:
            add_red_flag(
                result,
                f"row {row_number}: component_qty must be a positive integer",
            )
            continue

        cabinet_code = row["cabinet_code"]
        component_code = row["component_code"]
        component_label: str | None = None
        cabinet_label: str | None = None
        component_mapping: ApprovedComponentPriceMapping | None = None
        cabinet_mapping: ApprovedCabinetPriceMapping | None = None
        technical_mapping_validated = False

        if header_tuple in (TECHNICAL_COLUMNS, SHU_T2_TECHNICAL_COLUMNS):
            component_label = row["component_label"]
            cabinet_label = row["cabinet_label"]
            rt820_requested = component_code == RT820_COMPONENT_CODE
            component_mapping = resolve_case_scoped_rt820_mapping(row)
            if (
                component_mapping is not None
                and result.price_baseline_version == ACTIVE_VERSION
            ):
                component_mapping = next(
                    (
                        item
                        for item in selected_mappings
                        if item.mapping_id == component_mapping.mapping_id
                    ),
                    None,
                )
            component_signature = (
                RT820_APPROVED_MAPPING.signature
                if component_mapping is not None
                else parse_component_signature(
                    component_label,
                    row["install_type"],
                )
            )
            if not rt820_requested and component_signature is not None:
                component_mapping = resolve_component_mapping(
                    component_signature, component_code, selected_mappings
                )
            if component_mapping is None:
                if rt820_requested:
                    add_red_flag(
                        result,
                        f"row {row_number}: RT-820 is allowed only for the exact "
                        "project 2024/086 ШУ-Т1 or bound ШУ-Т2 "
                        "code/install/label contract; ask Igor",
                    )
                    continue
                legacy_definition = COMPONENT_DEFINITIONS.get(component_code)
                explicitly_validated = technical_component_definition_matches(
                    component_signature,
                    component_code,
                    row["install_type"],
                )
                legacy_compatible = (
                    parse_breaking_capacity_ka(component_label) is None
                    and legacy_definition is not None
                    and legacy_definition.install_type == row["install_type"]
                    and component_code != "EKF-AD32-1P-N"
                    and not exact_component_price_mapping_required(component_code)
                    and not (
                        component_signature is not None
                        and signature_requires_component_code(component_signature)
                    )
                )
                if not explicitly_validated and not legacy_compatible:
                    add_red_flag(
                        result,
                        f"row {row_number}: unknown or ambiguous technical "
                        f"component mapping for {component_label}; ask Igor",
                    )
                    continue
                technical_mapping_validated = explicitly_validated or legacy_compatible
            else:
                technical_mapping_validated = True

            cabinet_signature = parse_cabinet_signature(
                cabinet_code,
                cabinet_label,
            )
            cabinet_mapping = (
                resolve_cabinet_mapping(cabinet_signature, selected_cabinet_mappings)
                if cabinet_signature is not None
                else None
            )
            if cabinet_mapping is None and not technical_cabinet_definition_matches(
                cabinet_code,
                cabinet_label,
            ):
                add_red_flag(
                    result,
                    f"row {row_number}: unknown or ambiguous technical "
                    f"cabinet mapping for {cabinet_code} / {cabinet_label}; "
                    "ask Igor",
                )
                continue
        else:
            if component_code == RT820_COMPONENT_CODE:
                add_red_flag(
                    result,
                    f"row {row_number}: RT-820 requires the exact technical-label "
                    "contract; family or label-free fallback is prohibited; ask Igor",
                )
                continue
            component_definition = COMPONENT_DEFINITIONS.get(component_code)
            if component_definition is None:
                add_red_flag(
                    result,
                    f"row {row_number}: component_code is not confirmed: "
                    f"{component_code}; ask Igor",
                )
                continue
            if row["install_type"] != component_definition.install_type:
                add_red_flag(
                    result,
                    f"row {row_number}: install_type does not match confirmed "
                    f"component map for {component_code}; ask Igor",
                )
                continue
            if cabinet_code not in CABINET_DEFINITIONS:
                add_red_flag(
                    result,
                    f"row {row_number}: cabinet_code is not confirmed: "
                    f"{cabinet_code}; ask Igor",
                )
                continue

        rows.append(
            CompositionRow(
                product_name=row["product_name"],
                cabinet_code=cabinet_code,
                consumables_factor=factor,
                component_code=component_code,
                component_qty=int(quantity_text),
                install_type=row["install_type"],
                component_label=component_label,
                cabinet_label=cabinet_label,
                component_mapping=component_mapping,
                cabinet_mapping=cabinet_mapping,
                technical_mapping_validated=technical_mapping_validated,
            )
        )

    if len(rows) != len(raw_rows):
        return []

    product_names = {row.product_name for row in rows}
    cabinet_codes = {row.cabinet_code for row in rows}
    factors = {row.consumables_factor for row in rows}
    if len(product_names) != 1:
        add_red_flag(result, "all rows must have the same product_name")
    if len(cabinet_codes) != 1:
        add_red_flag(result, "all rows must have the same cabinet_code")
    if len(factors) != 1:
        add_red_flag(result, "all rows must have the same consumables_factor")
    if result.red_flags:
        return []

    result.product_name = rows[0].product_name
    result.cabinet_code = rows[0].cabinet_code
    result.cabinet_label = (
        rows[0].cabinet_label
        if rows[0].cabinet_label is not None
        else CABINET_DEFINITIONS[rows[0].cabinet_code]
    )
    result.consumables_factor = rows[0].consumables_factor
    return rows


def normalize_workbook_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return " ".join(value.replace("\xa0", " ").split())


def positive_integer_price(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value > 0 and value.is_integer() else None
    if isinstance(value, Decimal):
        integral = value.to_integral_value()
        return int(integral) if value > 0 and value == integral else None
    return None


def mapping_worksheet(
    workbook: Any,
    sheet_name: str,
    result: PriceCalculationResult,
) -> Any | None:
    if sheet_name.casefold() == FORBIDDEN_PRICE_SHEET_NAME.casefold():
        add_red_flag(result, "worksheet Прайс is forbidden for price lookup")
        return None
    try:
        return workbook[sheet_name]
    except KeyError:
        add_red_flag(result, f"required worksheet {sheet_name} was not found; ask Igor")
        return None


def read_approved_component_price(
    workbook: Any,
    mapping: ApprovedComponentPriceMapping,
    result: PriceCalculationResult,
) -> tuple[int, int] | None:
    if mapping not in component_price_mappings(
        result.price_baseline_version,
        result.price_mapping_snapshot,
    ):
        add_red_flag(result, "cross-version component price mapping mix; ask Igor")
        return None
    worksheet = mapping_worksheet(workbook, mapping.sheet_name, result)
    if worksheet is None:
        return None
    raw_label = worksheet.cell(mapping.row, 1).value
    actual_label = (
        raw_label if mapping.strict_raw_label else normalize_workbook_label(raw_label)
    )
    expected_label = (
        mapping.expected_label
        if mapping.strict_raw_label
        else normalize_workbook_label(mapping.expected_label)
    )
    if actual_label != expected_label:
        add_red_flag(
            result,
            f"approved component mapping signature mismatch at "
            f"{mapping.sheet_name}!A{mapping.row}: expected "
            f"{mapping.expected_label}; ask Igor",
        )
        return None
    material_price = positive_integer_price(worksheet.cell(mapping.row, 2).value)
    work_price = positive_integer_price(worksheet.cell(mapping.row, 3).value)
    if (
        material_price != mapping.expected_material_price
        or work_price != mapping.expected_work_price
    ):
        add_red_flag(
            result,
            f"approved component mapping price mismatch at "
            f"{mapping.sheet_name}!B{mapping.row}:C{mapping.row}; ask Igor",
        )
        return None
    return material_price, work_price


def read_approved_cabinet_price(
    workbook: Any,
    mapping: ApprovedCabinetPriceMapping,
    result: PriceCalculationResult,
) -> int | None:
    worksheet = mapping_worksheet(workbook, mapping.sheet_name, result)
    if worksheet is None:
        return None
    actual_label = normalize_workbook_label(worksheet.cell(mapping.row, 12).value)
    expected_label = normalize_workbook_label(mapping.expected_label)
    if actual_label != expected_label:
        add_red_flag(
            result,
            f"approved cabinet mapping signature mismatch at "
            f"{mapping.sheet_name}!L{mapping.row}: expected "
            f"{mapping.expected_label}; ask Igor",
        )
        return None
    price = positive_integer_price(worksheet.cell(mapping.row, 13).value)
    if price != mapping.expected_price:
        add_red_flag(
            result,
            f"approved cabinet mapping price mismatch at "
            f"{mapping.sheet_name}!M{mapping.row}; ask Igor",
        )
        return None
    return price


def read_component_prices(
    worksheet: Any,
    required_codes: set[str],
    result: PriceCalculationResult,
) -> dict[str, tuple[int, int]]:
    label_to_code = {
        normalize_workbook_label(definition.workbook_label): code
        for code, definition in COMPONENT_DEFINITIONS.items()
        if code in required_codes and definition.workbook_label is not None
    }
    found: dict[str, tuple[int, int]] = {}

    for label_value, material_value, work_value in worksheet.iter_rows(
        min_row=1,
        max_row=MAX_LOOKUP_ROW,
        min_col=1,
        max_col=3,
        values_only=True,
    ):
        label = normalize_workbook_label(label_value)
        code = label_to_code.get(label)
        if code is None:
            continue
        if code in found:
            add_red_flag(
                result,
                f"duplicate component price row in КРН for {code}; ask Igor",
            )
            continue

        material_price = positive_integer_price(material_value)
        work_price = positive_integer_price(work_value)
        if material_price is None:
            add_red_flag(
                result,
                f"material price is missing or invalid in КРН for {code}; ask Igor",
            )
        if work_price is None:
            add_red_flag(
                result,
                f"work price is missing or invalid in КРН for {code}; ask Igor",
            )
        if material_price is not None and work_price is not None:
            found[code] = (material_price, work_price)

    for code in sorted(required_codes - found.keys()):
        if not any(code in flag for flag in result.red_flags):
            add_red_flag(
                result,
                f"component price row was not found in КРН for {code}; ask Igor",
            )
    return found


def read_cabinet_price(
    worksheet: Any,
    cabinet_code: str,
    result: PriceCalculationResult,
) -> int | None:
    expected_label = normalize_workbook_label(CABINET_DEFINITIONS[cabinet_code])
    found_prices: list[int] = []

    for label_value, price_value in worksheet.iter_rows(
        min_row=1,
        max_row=MAX_LOOKUP_ROW,
        min_col=12,
        max_col=13,
        values_only=True,
    ):
        if normalize_workbook_label(label_value) != expected_label:
            continue
        price = positive_integer_price(price_value)
        if price is None:
            add_red_flag(
                result,
                f"cabinet price is missing or invalid in КРН for "
                f"{cabinet_code}; ask Igor",
            )
        else:
            found_prices.append(price)

    if not found_prices:
        if not any(cabinet_code in flag for flag in result.red_flags):
            add_red_flag(
                result,
                f"cabinet price row was not found in КРН for {cabinet_code}; ask Igor",
            )
        return None
    if len(found_prices) > 1:
        add_red_flag(
            result,
            f"duplicate cabinet price row in КРН for {cabinet_code}; ask Igor",
        )
        return None
    return found_prices[0]


def _snapshot_entry(
    *,
    mapping_id: str,
    mapping_kind: str,
    identity: Mapping[str, Any],
    sheet: str,
    row: int,
    label_cell: str,
    price_cells: list[str],
    prices: Mapping[str, int],
) -> dict[str, Any]:
    return {
        "mapping_id": mapping_id,
        "mapping_kind": mapping_kind,
        "identity": dict(identity),
        "identity_fingerprint": mapping_identity_fingerprint(identity),
        "source": {
            "sheet": sheet,
            "row": row,
            "label_cell": f"{sheet}!{label_cell}",
            "price_cells": [f"{sheet}!{cell}" for cell in price_cells],
        },
        "prices": dict(prices),
    }


def build_governed_mapping_snapshot(
    workbook: Any,
    *,
    component_mappings: tuple[ApprovedComponentPriceMapping, ...],
    cabinet_mappings: tuple[ApprovedCabinetPriceMapping, ...] = (
        APPROVED_CABINET_PRICE_MAPPINGS
    ),
) -> list[dict[str, Any]]:
    """Capture prices while keeping technical mapping identity price-free."""
    entries: list[dict[str, Any]] = []
    for component_mapping in component_mappings:
        worksheet = workbook[component_mapping.sheet_name]
        raw_label = worksheet.cell(component_mapping.row, 1).value
        actual_label = (
            raw_label
            if component_mapping.strict_raw_label
            else normalize_workbook_label(raw_label)
        )
        expected_label = (
            component_mapping.expected_label
            if component_mapping.strict_raw_label
            else normalize_workbook_label(component_mapping.expected_label)
        )
        material = positive_integer_price(
            worksheet.cell(component_mapping.row, 2).value
        )
        work = positive_integer_price(worksheet.cell(component_mapping.row, 3).value)
        if actual_label != expected_label or material is None or work is None:
            raise ValueError(
                f"governed mapping cannot be captured: {component_mapping.mapping_id}"
            )
        entries.append(
            _snapshot_entry(
                mapping_id=component_mapping.mapping_id,
                mapping_kind="component_exact",
                identity=component_mapping_identity(component_mapping),
                sheet=component_mapping.sheet_name,
                row=component_mapping.row,
                label_cell=f"A{component_mapping.row}",
                price_cells=[
                    f"B{component_mapping.row}",
                    f"C{component_mapping.row}",
                ],
                prices={"material_kzt": material, "work_kzt": work},
            )
        )
    krn = workbook[KRN_SHEET_NAME]
    for component_code, definition in COMPONENT_DEFINITIONS.items():
        if definition.workbook_label is None:
            continue
        expected_label = normalize_workbook_label(definition.workbook_label)
        component_matches: list[tuple[int, int, int]] = []
        for row in range(1, MAX_LOOKUP_ROW + 1):
            if normalize_workbook_label(krn.cell(row, 1).value) != expected_label:
                continue
            material = positive_integer_price(krn.cell(row, 2).value)
            work = positive_integer_price(krn.cell(row, 3).value)
            if material is not None and work is not None:
                component_matches.append((row, material, work))
        if len(component_matches) != 1:
            raise ValueError(
                f"dynamic component mapping is missing or ambiguous: {component_code}"
            )
        row, material, work = component_matches[0]
        mapping_id = f"COMPONENT-DYNAMIC-{component_code}"
        identity = {
            "authority": "TECHNICAL_MAPPING_IDENTITY",
            "mapping_id": mapping_id,
            "component_code": component_code,
            "install_type": definition.install_type,
            "sheet": KRN_SHEET_NAME,
            "row": row,
            "expected_label": definition.workbook_label,
            "strict_label": False,
            "lookup_semantics": "unique_normalized_label",
        }
        entries.append(
            _snapshot_entry(
                mapping_id=mapping_id,
                mapping_kind="component_dynamic",
                identity=identity,
                sheet=KRN_SHEET_NAME,
                row=row,
                label_cell=f"A{row}",
                price_cells=[f"B{row}", f"C{row}"],
                prices={"material_kzt": material, "work_kzt": work},
            )
        )
    for cabinet_mapping in cabinet_mappings:
        worksheet = workbook[cabinet_mapping.sheet_name]
        actual_label = normalize_workbook_label(
            worksheet.cell(cabinet_mapping.row, 12).value
        )
        expected_label = normalize_workbook_label(cabinet_mapping.expected_label)
        price = positive_integer_price(worksheet.cell(cabinet_mapping.row, 13).value)
        if actual_label != expected_label or price is None:
            raise ValueError(
                f"governed mapping cannot be captured: {cabinet_mapping.mapping_id}"
            )
        entries.append(
            _snapshot_entry(
                mapping_id=cabinet_mapping.mapping_id,
                mapping_kind="cabinet_exact",
                identity=cabinet_mapping_identity(cabinet_mapping),
                sheet=cabinet_mapping.sheet_name,
                row=cabinet_mapping.row,
                label_cell=f"L{cabinet_mapping.row}",
                price_cells=[f"M{cabinet_mapping.row}"],
                prices={"price_kzt": price},
            )
        )
    for cabinet_code, expected in CABINET_DEFINITIONS.items():
        if cabinet_code == INVOICE519_SCHE_CABINET_CODE:
            continue
        expected_label = normalize_workbook_label(expected)
        cabinet_matches: list[tuple[int, int]] = []
        for row in range(1, MAX_LOOKUP_ROW + 1):
            if normalize_workbook_label(krn.cell(row, 12).value) != expected_label:
                continue
            price = positive_integer_price(krn.cell(row, 13).value)
            if price is not None:
                cabinet_matches.append((row, price))
        if len(cabinet_matches) != 1:
            raise ValueError(
                f"dynamic cabinet mapping is missing or ambiguous: {cabinet_code}"
            )
        row, cabinet_price = cabinet_matches[0]
        mapping_id = f"CABINET-DYNAMIC-{cabinet_code}"
        identity = {
            "authority": "TECHNICAL_MAPPING_IDENTITY",
            "mapping_id": mapping_id,
            "cabinet_code": cabinet_code,
            "sheet": KRN_SHEET_NAME,
            "row": row,
            "expected_label": expected,
            "strict_label": False,
            "lookup_semantics": "unique_normalized_label",
        }
        entries.append(
            _snapshot_entry(
                mapping_id=mapping_id,
                mapping_kind="cabinet_dynamic",
                identity=identity,
                sheet=KRN_SHEET_NAME,
                row=row,
                label_cell=f"L{row}",
                price_cells=[f"M{row}"],
                prices={"price_kzt": cabinet_price},
            )
        )
    return sorted(entries, key=lambda entry: cast(str, entry["mapping_id"]))


def calculate_price_draft(
    price_workbook: Path | None,
    input_csv: Path,
    custom_cabinet_base_cost: int | None = None,
    price_baseline_version: str | None = None,
    active_selector_path: Path = DEFAULT_ACTIVE_SELECTOR,
) -> PriceCalculationResult:
    requested_workbook = (
        resolved(price_workbook) if price_workbook is not None else None
    )
    selected_version = (
        ACTIVE_VERSION if price_baseline_version is None else price_baseline_version
    )
    result = PriceCalculationResult(
        price_workbook=requested_workbook or Path("<active-price-workbook>"),
        input_csv=resolved(input_csv),
        price_baseline_version=selected_version,
        active_selector_path=resolved(active_selector_path),
    )
    try:
        if price_baseline_version is None:
            baseline = resolve_price_baseline(
                requested_workbook,
                None,
                active_selector_path=result.active_selector_path,
            )
        elif price_baseline_version == ACTIVE_VERSION:
            baseline = require_price_baseline(
                requested_workbook,
                ACTIVE_VERSION,
                active_selector_path=result.active_selector_path,
            )
        else:
            baseline = require_price_baseline(
                requested_workbook,
                price_baseline_version,
            )
    except ValueError as exc:
        add_red_flag(result, str(exc))
        return result
    if baseline.version == ACTIVE_VERSION:
        result.price_workbook = baseline.path
    result.price_baseline_version = baseline.version
    result.price_baseline_sha256 = baseline.sha256
    result.price_baseline_manifest_id = baseline.manifest_id
    result.price_baseline_manifest_sha256 = baseline.manifest_sha256
    result.price_mapping_snapshot = baseline.mapping_snapshot
    rows = load_composition_rows(result)
    if not rows:
        return result

    workbook_path = result.price_workbook
    if not workbook_path.is_file():
        add_red_flag(result, f"price workbook does not exist: {workbook_path}")
        return result
    if workbook_path.suffix.casefold() != ".xlsx":
        add_red_flag(result, "price workbook suffix must be .xlsx")
        return result

    workbook: Any | None = None
    try:
        workbook = load_workbook(
            filename=workbook_path,
            read_only=True,
            data_only=False,
            keep_links=False,
        )
        approved_component_prices: dict[
            ApprovedComponentPriceMapping, tuple[int, int]
        ] = {}
        for row in rows:
            mapping = row.component_mapping
            if mapping is not None and mapping not in approved_component_prices:
                price = read_approved_component_price(workbook, mapping, result)
                if price is not None:
                    approved_component_prices[mapping] = price

        worksheet = mapping_worksheet(workbook, KRN_SHEET_NAME, result)
        if worksheet is None:
            return result
        required_codes = {
            row.component_code for row in rows if row.component_mapping is None
        }
        component_prices: dict[str, tuple[int, int]] = {}
        if required_codes:
            component_prices = read_component_prices(
                worksheet,
                required_codes,
                result,
            )

        cabinet_mapping = rows[0].cabinet_mapping
        if any(row.cabinet_mapping != cabinet_mapping for row in rows):
            add_red_flag(result, "technical cabinet mapping is inconsistent; ask Igor")
            cabinet_price = None
        elif rows[0].cabinet_code == "CAB-SCHE-BI-900X900X120-M12":
            if custom_cabinet_base_cost is None or custom_cabinet_base_cost <= 0:
                add_red_flag(
                    result,
                    "checked custom ЩЭ cabinet base cost is required; ask Igor",
                )
                cabinet_price = None
            else:
                cabinet_price = custom_cabinet_base_cost
        elif cabinet_mapping is not None:
            cabinet_price = read_approved_cabinet_price(
                workbook,
                cabinet_mapping,
                result,
            )
        else:
            cabinet_price = read_cabinet_price(
                worksheet,
                rows[0].cabinet_code,
                result,
            )
    except (OSError, ValueError):  # fmt: skip
        add_red_flag(result, "price workbook could not be opened safely")
        return result
    finally:
        if workbook is not None:
            workbook.close()

    try:
        if result.price_baseline_version == ACTIVE_VERSION:
            require_price_baseline(
                result.price_workbook,
                ACTIVE_VERSION,
                active_selector_path=result.active_selector_path,
            )
        else:
            require_price_baseline(
                result.price_workbook,
                result.price_baseline_version,
            )
    except ValueError as exc:
        add_red_flag(result, f"price baseline final drift: {exc}")
        return result

    if result.red_flags or cabinet_price is None:
        return result

    material_total = sum(
        (
            approved_component_prices[row.component_mapping][0]
            if row.component_mapping is not None
            else component_prices[row.component_code][0]
        )
        * row.component_qty
        for row in rows
    )
    work_total = sum(
        (
            approved_component_prices[row.component_mapping][1]
            if row.component_mapping is not None
            else component_prices[row.component_code][1]
        )
        * row.component_qty
        for row in rows
    )
    factor = rows[0].consumables_factor
    additional_materials = Decimal(material_total) * (factor - Decimal("1"))
    base = (
        Decimal(cabinet_price)
        + Decimal(material_total)
        + additional_materials
        + Decimal(work_total)
    )
    total = int(
        (base * MATERIAL_MULTIPLIER * FINAL_MULTIPLIER).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )

    result.cabinet_price = cabinet_price
    result.component_material_total = material_total
    result.work_total = work_total
    result.additional_materials_total = additional_materials
    result.base = base
    result.total_preliminary_price = total
    result.status = "PASS"
    return result


def format_amount(value: int | Decimal | None) -> str:
    if value is None:
        return "not calculated"
    decimal_value = Decimal(value)
    if decimal_value == decimal_value.to_integral_value():
        return f"{int(decimal_value):,}".replace(",", " ")
    integer_part, fractional_part = format(decimal_value.normalize(), "f").split(".")
    grouped_integer = f"{int(integer_part):,}".replace(",", " ")
    return f"{grouped_integer}.{fractional_part}"


def format_red_flags(red_flags: Sequence[str]) -> list[str]:
    if not red_flags:
        return ["none"]
    return [f"- {flag}" for flag in red_flags]


def format_report(result: PriceCalculationResult) -> str:
    cabinet = "not resolved"
    if result.cabinet_code is not None and result.cabinet_label is not None:
        cabinet = f"{result.cabinet_code} / {result.cabinet_label}"
    factor = (
        f"{result.consumables_factor:.2f}"
        if result.consumables_factor is not None
        else "not resolved"
    )
    lines = [
        "PRICE_CALCULATION_DRAFT_REPORT_START",
        "",
        "Status:",
        result.status,
        "",
        "Mode:",
        "read-only preliminary price draft",
        "",
        "Product name:",
        result.product_name or "not resolved",
        "",
        "Workbook path:",
        str(result.price_workbook),
        "",
        "Price baseline version:",
        result.price_baseline_version,
        "",
        "Price baseline SHA-256:",
        result.price_baseline_sha256 or "not validated",
        "",
        "Price baseline manifest ID:",
        result.price_baseline_manifest_id or "explicit static/frozen binding",
        "",
        "Price baseline manifest SHA-256:",
        result.price_baseline_manifest_sha256 or "not applicable",
        "",
        "Input CSV path:",
        str(result.input_csv),
        "",
        "Input rows count:",
        str(result.input_rows_count),
        "",
        "Cabinet:",
        cabinet,
        "",
        "Cabinet price:",
        format_amount(result.cabinet_price),
        "",
        "Component material total:",
        format_amount(result.component_material_total),
        "",
        "Work total:",
        format_amount(result.work_total),
        "",
        "Additional materials total:",
        format_amount(result.additional_materials_total),
        "",
        "Consumables factor:",
        factor,
        "",
        "Base:",
        format_amount(result.base),
        "",
        "Total preliminary price:",
        format_amount(result.total_preliminary_price),
        "",
        "Red flags:",
    ]
    lines.extend(format_red_flags(result.red_flags))
    lines.extend(
        [
            "",
            "Commercial status:",
            "preliminary only; PASS is not commercial approval",
            "",
            "Before transfer to commercial CSV:",
            "Igor approval required",
            "",
            "Manual Igor check:",
            "required",
            "",
            "Human Approval:",
            "required before using price in commercial КП",
            "",
            "PRICE_CALCULATION_DRAFT_REPORT_END",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = calculate_price_draft(
        args.price_workbook,
        args.input_csv,
        custom_cabinet_base_cost=args.custom_cabinet_base_cost,
        price_baseline_version=args.price_baseline_version,
        active_selector_path=args.active_selector,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
