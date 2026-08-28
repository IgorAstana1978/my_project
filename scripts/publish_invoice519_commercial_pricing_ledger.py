"""Publish one immutable 88-position commercial pricing ledger for Invoice 519."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
APPLICATION_PUBLISHER_PATH = Path(__file__).with_name(
    "publish_invoice519_price_application.py"
)
SCHEMA_VERSION = "invoice519_commercial_pricing_ledger.v0.1"
SCHEMA_FILENAME = "invoice519_commercial_pricing_ledger_v0_1.schema.json"
SCHEMA_PATH = REPO_ROOT / "schemas" / SCHEMA_FILENAME
OUTPUT_FILENAME = "invoice519-commercial-pricing-ledger-v0.1.json"
PROJECT_ID = "2024/086"
INVOICE_NUMBER = 519
LEDGER_ID = "IGOR-INVOICE519-COMMERCIAL-PRICING-LEDGER-2024-086-001"
STATUS = "IGOR_INVOICE519_88_POSITION_PRICING_LEDGER_READY_QUOTE_NOT_GENERATED"
AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
PRICING_SCOPE = "PRICE_ONLY_88_POSITIONS"
APPLICATION_STATUS = "APPLIED"
APPROVED_TOTAL_KZT = 19_499_186
FROZEN_SUBTOTAL_KZT = 11_963_792
MISSING_SUBTOTAL_KZT = 7_535_394
PREDECESSOR_PATH = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-"
    "2024-086-INVOICE519-PRICE-APPLICATION-20260828-001\\"
    "invoice519-price-application-v0.1.json"
)
PREDECESSOR_SHA256 = "bd86761261a0560cf29649e081769a4d85dcc175ee4f20fd3186f64bd64bcbb0"
PUBLICATION_AUTHORIZATION = (
    "IGOR_INVOICE519_COMMERCIAL_PRICING_LEDGER_PUBLICATION_AUTHORIZED"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CREATED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# Exact final checked-calculator position capture. The four SHU-T2 successor
# rows and four SHU-T1 successor rows are the already checked 53,763 KZT grain;
# no workbook or price formula is evaluated by this publisher.
FROZEN_EVIDENCE = (
    (
        6,
        1,
        54023,
        54023,
        "PRICE-POSITION-001",
        "e7bd747e63214dcd11d5d9bdc0f4ad1de01fe63f6b4098f4e9f2f922c3dc7a0e",
    ),
    (
        7,
        1,
        27677,
        27677,
        "PRICE-POSITION-004",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        8,
        1,
        27677,
        27677,
        "PRICE-POSITION-002",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        9,
        1,
        27677,
        27677,
        "PRICE-POSITION-005",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        10,
        1,
        27677,
        27677,
        "PRICE-POSITION-003",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        11,
        1,
        53763,
        53763,
        "PRICE-POSITION-052",
        "4b5cf23236653dfd33e27eefa8034ad2a779b5e2b40f0adc972ee49912dbc0ec",
    ),
    (
        12,
        1,
        96270,
        96270,
        "PRICE-POSITION-006",
        "f35921dbb25f36bb05b1ac7c9565daa2497e37409dfaf38019537f0de819d4de",
    ),
    (
        13,
        9,
        112127,
        1009143,
        "PRICE-POSITION-007",
        "35f692f40bdbba41d7c33f072e011e97a5feff21b4f7dd32f7d665eb4d1ee3af",
    ),
    (
        14,
        8,
        127984,
        1023872,
        "PRICE-POSITION-008",
        "710e6c965fff027ae5f209a6d8b0310a9364cb88bb51252bae1feac300fa4d38",
    ),
    (
        16,
        1,
        27677,
        27677,
        "PRICE-POSITION-011",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        17,
        1,
        27677,
        27677,
        "PRICE-POSITION-010",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        18,
        1,
        53763,
        53763,
        "PRICE-POSITION-009",
        "4b5cf23236653dfd33e27eefa8034ad2a779b5e2b40f0adc972ee49912dbc0ec",
    ),
    (
        19,
        1,
        96270,
        96270,
        "PRICE-POSITION-012",
        "f35921dbb25f36bb05b1ac7c9565daa2497e37409dfaf38019537f0de819d4de",
    ),
    (
        20,
        8,
        112127,
        897016,
        "PRICE-POSITION-013",
        "35f692f40bdbba41d7c33f072e011e97a5feff21b4f7dd32f7d665eb4d1ee3af",
    ),
    (
        27,
        1,
        59166,
        59166,
        "PRICE-POSITION-014",
        "a1c855a54373b61d68c5e66ef2f3f2a407faf2afdc46a159ff688d10eb3adaab",
    ),
    (
        30,
        1,
        56993,
        56993,
        "PRICE-POSITION-019",
        "b5e46867e8e6c2d601ae85fbba46083a2b5d8d3d02e38eff7ab3cec909511d3e",
    ),
    (
        31,
        1,
        27677,
        27677,
        "PRICE-POSITION-017",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        32,
        1,
        27677,
        27677,
        "PRICE-POSITION-015",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        33,
        1,
        27677,
        27677,
        "PRICE-POSITION-018",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        34,
        1,
        27677,
        27677,
        "PRICE-POSITION-016",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        35,
        1,
        53763,
        53763,
        "PRICE-POSITION-053",
        "4b5cf23236653dfd33e27eefa8034ad2a779b5e2b40f0adc972ee49912dbc0ec",
    ),
    (
        36,
        1,
        80413,
        80413,
        "PRICE-POSITION-020",
        "04094094a360e9c2ee9a6cc7ff6191809c8983391dca13be0b4edff35253e90c",
    ),
    (
        37,
        9,
        96270,
        866430,
        "PRICE-POSITION-021",
        "f35921dbb25f36bb05b1ac7c9565daa2497e37409dfaf38019537f0de819d4de",
    ),
    (
        39,
        1,
        27677,
        27677,
        "PRICE-POSITION-025",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        40,
        1,
        27677,
        27677,
        "PRICE-POSITION-024",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        41,
        1,
        53763,
        53763,
        "PRICE-POSITION-023",
        "4b5cf23236653dfd33e27eefa8034ad2a779b5e2b40f0adc972ee49912dbc0ec",
    ),
    (
        42,
        1,
        96270,
        96270,
        "PRICE-POSITION-026",
        "f35921dbb25f36bb05b1ac7c9565daa2497e37409dfaf38019537f0de819d4de",
    ),
    (
        43,
        8,
        112127,
        897016,
        "PRICE-POSITION-027",
        "35f692f40bdbba41d7c33f072e011e97a5feff21b4f7dd32f7d665eb4d1ee3af",
    ),
    (
        50,
        1,
        54023,
        54023,
        "PRICE-POSITION-028",
        "e7bd747e63214dcd11d5d9bdc0f4ad1de01fe63f6b4098f4e9f2f922c3dc7a0e",
    ),
    (
        51,
        1,
        27677,
        27677,
        "PRICE-POSITION-031",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        52,
        1,
        27677,
        27677,
        "PRICE-POSITION-029",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        53,
        1,
        27677,
        27677,
        "PRICE-POSITION-032",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        54,
        1,
        27677,
        27677,
        "PRICE-POSITION-030",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        55,
        1,
        53763,
        53763,
        "PRICE-POSITION-054",
        "4b5cf23236653dfd33e27eefa8034ad2a779b5e2b40f0adc972ee49912dbc0ec",
    ),
    (
        56,
        10,
        96270,
        962700,
        "PRICE-POSITION-033",
        "f35921dbb25f36bb05b1ac7c9565daa2497e37409dfaf38019537f0de819d4de",
    ),
    (
        57,
        8,
        112127,
        897016,
        "PRICE-POSITION-034",
        "35f692f40bdbba41d7c33f072e011e97a5feff21b4f7dd32f7d665eb4d1ee3af",
    ),
    (
        59,
        1,
        27677,
        27677,
        "PRICE-POSITION-037",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        60,
        1,
        27677,
        27677,
        "PRICE-POSITION-036",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        61,
        1,
        53763,
        53763,
        "PRICE-POSITION-035",
        "4b5cf23236653dfd33e27eefa8034ad2a779b5e2b40f0adc972ee49912dbc0ec",
    ),
    (
        62,
        1,
        96270,
        96270,
        "PRICE-POSITION-038",
        "f35921dbb25f36bb05b1ac7c9565daa2497e37409dfaf38019537f0de819d4de",
    ),
    (
        63,
        8,
        112127,
        897016,
        "PRICE-POSITION-039",
        "35f692f40bdbba41d7c33f072e011e97a5feff21b4f7dd32f7d665eb4d1ee3af",
    ),
    (
        70,
        1,
        59166,
        59166,
        "PRICE-POSITION-040",
        "a1c855a54373b61d68c5e66ef2f3f2a407faf2afdc46a159ff688d10eb3adaab",
    ),
    (
        73,
        1,
        56993,
        56993,
        "PRICE-POSITION-045",
        "b5e46867e8e6c2d601ae85fbba46083a2b5d8d3d02e38eff7ab3cec909511d3e",
    ),
    (
        74,
        1,
        30123,
        30123,
        "PRICE-POSITION-043",
        "5db2d05963f2e44a139909842ca95cd1c7495ebe2cb1bb8d6000edfa60ef7408",
    ),
    (
        75,
        1,
        27677,
        27677,
        "PRICE-POSITION-041",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        76,
        1,
        27677,
        27677,
        "PRICE-POSITION-044",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        77,
        1,
        27677,
        27677,
        "PRICE-POSITION-042",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        78,
        1,
        53763,
        53763,
        "PRICE-POSITION-055",
        "4b5cf23236653dfd33e27eefa8034ad2a779b5e2b40f0adc972ee49912dbc0ec",
    ),
    (
        79,
        16,
        96270,
        1540320,
        "PRICE-POSITION-046",
        "f35921dbb25f36bb05b1ac7c9565daa2497e37409dfaf38019537f0de819d4de",
    ),
    (
        81,
        1,
        27677,
        27677,
        "PRICE-POSITION-049",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        82,
        1,
        27677,
        27677,
        "PRICE-POSITION-048",
        "be5b90604085896d89dced03fe78f6b8ccb909902d8862bc91d99071648d175b",
    ),
    (
        83,
        1,
        53763,
        53763,
        "PRICE-POSITION-047",
        "4b5cf23236653dfd33e27eefa8034ad2a779b5e2b40f0adc972ee49912dbc0ec",
    ),
    (
        84,
        1,
        96270,
        96270,
        "PRICE-POSITION-050",
        "f35921dbb25f36bb05b1ac7c9565daa2497e37409dfaf38019537f0de819d4de",
    ),
    (
        85,
        8,
        112127,
        897016,
        "PRICE-POSITION-051",
        "35f692f40bdbba41d7c33f072e011e97a5feff21b4f7dd32f7d665eb4d1ee3af",
    ),
    (
        88,
        1,
        77322,
        77322,
        "PRICE-POSITION-022",
        "e634eb6e9cb6b2a3be01c8d508d8783e2274a7339591719142633dfaea0f1d12",
    ),
)

MISSING_EVIDENCE = (
    (1, 1, 395056, 395056, "VSHZH_VRU"),
    (2, 1, 258197, 258197, "RSHZH"),
    (3, 1, 517406, 517406, "AVR"),
    (4, 1, 232855, 232855, "SHCHSP"),
    (5, 1, 134720, 134720, "UKRM"),
    (15, 2, 43156, 86312, "YARV100"),
    (21, 1, 43156, 43156, "YARV100"),
    (22, 1, 395056, 395056, "VSHZH_VRU"),
    (23, 1, 254121, 254121, "RSHZH"),
    (24, 1, 517406, 517406, "AVR"),
    (25, 1, 232855, 232855, "SHCHSP"),
    (26, 1, 134720, 134720, "UKRM"),
    (28, 1, 233464, 233464, "VSHCHO"),
    (29, 1, 154165, 154165, "RSHCHO"),
    (38, 2, 43156, 86312, "YARV100"),
    (44, 1, 43156, 43156, "YARV100"),
    (45, 1, 398622, 398622, "VSHZH_VRU"),
    (46, 1, 254121, 254121, "RSHZH"),
    (47, 1, 517406, 517406, "AVR"),
    (48, 1, 232855, 232855, "SHCHSP"),
    (49, 1, 134720, 134720, "UKRM"),
    (58, 2, 43156, 86312, "YARV100"),
    (64, 1, 43156, 43156, "YARV100"),
    (65, 1, 395056, 395056, "VSHZH_VRU"),
    (66, 1, 254121, 254121, "RSHZH"),
    (67, 1, 517406, 517406, "AVR"),
    (68, 1, 232855, 232855, "SHCHSP"),
    (69, 1, 134720, 134720, "UKRM"),
    (71, 1, 233464, 233464, "VSHCHO"),
    (72, 1, 172409, 172409, "RSHCHO"),
    (80, 2, 43156, 86312, "YARV100"),
    (86, 1, 43156, 43156, "YARV100"),
    (87, 1, 79746, 79746, "YAUO9601_3474"),
)

CANONICAL_DATA_ROWS = tuple(
    row for row in range(17, 113) if row not in {32, 39, 57, 64, 79, 86, 103, 110}
)
FAMILY_BINDING_ROLES = {
    "UKRM": "ukrm_price_workbook",
    "YARV100": "yarv100_price_workbook",
}
PRICE_GRAIN = {
    "unit_price_rounding_mode": "ROUND_HALF_UP",
    "unit_price_rounding_stage": "AFTER_FULL_UNIT_PRICE_FORMULA",
    "position_total_grain": "APPROVED_UNIT_PRICE_TIMES_CANONICAL_QUANTITY",
    "unit_prices_recalculated": False,
    "arbitrary_allocation_used": False,
}
SAFETY = {
    "human_decision_recorded": True,
    "price_approved": True,
    "price_application_authorized": True,
    "price_applied": True,
    "commercial_pricing_ledger_recorded": True,
    "quote_generation_authorized": False,
    "invoice_generation_authorized": False,
    "quote_or_invoice_publication_authorized": False,
    "client_send_authorized": False,
    "procurement_authorized": False,
    "reserve_authorized": False,
    "prepayment_authorized": False,
    "production_authorized": False,
    "downstream_authorized": False,
}
PUBLICATION_CONTROL = {
    "immutable": True,
    "no_overwrite": True,
    "atomic_publication": True,
    "input_toctou_recheck_required": True,
    "final_strict_json_reread_required": True,
    "authorization_token_required": True,
}


def load_application_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "publish_invoice519_price_application_for_ledger",
        APPLICATION_PUBLISHER_PATH,
    )
    if spec is None or spec.loader is None:  # pragma: no cover - import bootstrap
        raise RuntimeError("Invoice 519 price application publisher is missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


application = load_application_module()


class ContractError(ValueError):
    """The requested ledger would violate the closed commercial contract."""


@dataclass(frozen=True)
class LoadedPredecessor:
    path: Path
    raw: bytes
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class PublicationResult:
    sha256: str
    size: int
    encoded: bytes


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require_mapping(value: Any, description: str) -> Mapping[str, Any]:
    require(isinstance(value, Mapping), f"{description} must be an object")
    return cast(Mapping[str, Any], value)


def require_list(value: Any, description: str) -> list[Any]:
    require(isinstance(value, list), f"{description} must be an array")
    return cast(list[Any], value)


def load_json(path: Path, description: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = application.predecessor.load_json_bytes(raw, description)
    except OSError as exc:
        raise ContractError(f"{description} could not be read: {exc}") from exc
    except application.predecessor.ContractError as exc:
        raise ContractError(str(exc)) from exc
    return dict(value), raw


def _validate_predecessor_payload(payload: Mapping[str, Any]) -> None:
    try:
        application.validate_payload(payload)
    except application.ContractError as exc:
        raise ContractError(f"predecessor contract mismatch: {exc}") from exc
    require(payload.get("schema_version") == application.SCHEMA_VERSION, "schema")
    require(payload.get("application_id") == application.APPLICATION_ID, "ID")
    require(payload.get("status") == application.STATUS, "status")
    require(payload.get("application_scope") == "PRICE_ONLY", "scope")
    require(payload.get("application_status") == "APPLIED", "application status")
    price = require_mapping(payload.get("price_application"), "price application")
    require(price.get("applied_price_kzt") == APPROVED_TOTAL_KZT, "applied price")
    require(
        payload.get("reconciliation")
        == application.predecessor._reconciliation_payload(),
        "reconciliation",
    )
    require(
        payload.get("technical_composition") == application._technical_composition(),
        "technical composition",
    )
    require(payload.get("safety") == application.SAFETY, "predecessor safety")


def load_and_validate_predecessor(
    path: Path, expected_sha256: str
) -> LoadedPredecessor:
    require(
        SHA256_RE.fullmatch(expected_sha256) is not None,
        "predecessor expected SHA format",
    )
    require(expected_sha256 == PREDECESSOR_SHA256, "predecessor SHA binding mismatch")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"predecessor path unavailable: {exc}") from exc
    require(
        resolved == PREDECESSOR_PATH.resolve(strict=False),
        "predecessor path binding mismatch",
    )
    payload, raw = load_json(resolved, "price application predecessor")
    require(sha256_bytes(raw) == PREDECESSOR_SHA256, "predecessor initial SHA mismatch")
    _validate_predecessor_payload(payload)
    return LoadedPredecessor(resolved, raw, payload)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _predecessor_binding(loaded: LoadedPredecessor) -> dict[str, Any]:
    binding = _expected_predecessor_binding()
    binding["path"] = str(loaded.path)
    binding["actual_sha256"] = sha256_bytes(loaded.raw)
    return binding


def _expected_predecessor_binding() -> dict[str, Any]:
    return {
        "role": "price_application",
        "path": str(PREDECESSOR_PATH.resolve(strict=False)),
        "expected_sha256": PREDECESSOR_SHA256,
        "actual_sha256": PREDECESSOR_SHA256,
        "schema_version": application.SCHEMA_VERSION,
        "application_id": application.APPLICATION_ID,
        "status": application.STATUS,
        "application_status": "APPLIED",
    }


def _technical_reference(position: int) -> dict[str, Any]:
    return {
        "source_binding_role": "canonical_invoice_519",
        "worksheet": "Лист1",
        "row": CANONICAL_DATA_ROWS[position - 1],
        "composition_status": "UNCHANGED_FROM_PRICE_APPLICATION_PREDECESSOR",
    }


def _positions_payload() -> list[dict[str, Any]]:
    positions: dict[int, dict[str, Any]] = {}
    for position, quantity, unit, total, pricing_id, fingerprint in FROZEN_EVIDENCE:
        positions[position] = {
            "invoice_position_number": position,
            "quantity": quantity,
            "approved_unit_price_kzt": unit,
            "approved_position_total_kzt": total,
            "currency": "KZT",
            "pricing_provenance": {
                "partition": "FROZEN_55",
                "evidence_role": "REAL_CHECKED_CALCULATOR_RUN_PASS",
                "source_binding_role": "pricing_profile",
                "source_reference": f"{pricing_id}|{fingerprint}",
                "allocation_method": "DIRECT_CHECKED_POSITION_PRICE",
                "price_recalculated": False,
            },
            "technical_description_reference": _technical_reference(position),
        }
    for position, quantity, unit, total, family in MISSING_EVIDENCE:
        positions[position] = {
            "invoice_position_number": position,
            "quantity": quantity,
            "approved_unit_price_kzt": unit,
            "approved_position_total_kzt": total,
            "currency": "KZT",
            "pricing_provenance": {
                "partition": "CHECKED_MISSING_33",
                "evidence_role": "NINE_FAMILY_READ_ONLY_CHECKS_PASS",
                "source_binding_role": FAMILY_BINDING_ROLES.get(
                    family, "main_price_workbook"
                ),
                "source_reference": f"FAMILY={family}",
                "allocation_method": "DIRECT_CHECKED_FAMILY_POSITION_PRICE",
                "price_recalculated": False,
            },
            "technical_description_reference": _technical_reference(position),
        }
    return [positions[position] for position in range(1, 89)]


def _ledger_summary() -> dict[str, Any]:
    return {
        "currency": "KZT",
        "position_count": 88,
        "approved_total_kzt": APPROVED_TOTAL_KZT,
        "derived_line_total_kzt": APPROVED_TOTAL_KZT,
        "frozen_55_subtotal_kzt": FROZEN_SUBTOTAL_KZT,
        "checked_missing_33_subtotal_kzt": MISSING_SUBTOTAL_KZT,
        "duplicates": 0,
        "missing": 0,
        "extra": 0,
        "unit_price_allocation_used": False,
        "price_recalculation_used": False,
        "technical_composition_changed": False,
    }


def build_payload(
    loaded: LoadedPredecessor, created_at_utc: str | None = None
) -> dict[str, Any]:
    created = created_at_utc or utc_now()
    require(CREATED_AT_RE.fullmatch(created) is not None, "created_at_utc format")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "IMMUTABLE_COMMERCIAL_PRICING_LEDGER_SUCCESSOR",
        "project_id": PROJECT_ID,
        "invoice_number": INVOICE_NUMBER,
        "ledger_id": LEDGER_ID,
        "status": STATUS,
        "authority": AUTHORITY,
        "pricing_scope": PRICING_SCOPE,
        "application_status": APPLICATION_STATUS,
        "created_at_utc": created,
        "predecessor": _predecessor_binding(loaded),
        "source_input_bindings": copy.deepcopy(loaded.payload["source_input_bindings"]),
        "price_grain": copy.deepcopy(PRICE_GRAIN),
        "positions": _positions_payload(),
        "ledger_summary": _ledger_summary(),
        "reconciliation": copy.deepcopy(loaded.payload["reconciliation"]),
        "technical_composition": copy.deepcopy(loaded.payload["technical_composition"]),
        "safety": copy.deepcopy(SAFETY),
        "publication_control": copy.deepcopy(PUBLICATION_CONTROL),
    }
    validate_payload(payload)
    return payload


def load_schema() -> dict[str, Any]:
    schema, _raw = load_json(SCHEMA_PATH, "committed commercial pricing ledger schema")
    require(
        schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
        "schema dialect mismatch",
    )
    require(schema.get("type") == "object", "schema root type mismatch")
    require(schema.get("additionalProperties") is False, "schema must be closed")
    properties = require_mapping(schema.get("properties"), "schema properties")
    version = require_mapping(properties.get("schema_version"), "schema version")
    require(version.get("const") == SCHEMA_VERSION, "schema version contract")
    return schema


def _validate_source_bindings(value: Any) -> None:
    bindings = require_list(value, "source input bindings")
    require(
        len(bindings) == len(application.predecessor.INPUT_SPECS), "input binding count"
    )
    for binding, spec in zip(
        bindings, application.predecessor.INPUT_SPECS, strict=True
    ):
        item = require_mapping(binding, "source input binding")
        require(item.get("role") == spec.role, f"{spec.role} role mismatch")
        require(item.get("path") == spec.path, f"{spec.role} path mismatch")
        require(
            item.get("expected_sha256") == spec.sha256,
            f"{spec.role} expected SHA mismatch",
        )
        require(
            item.get("actual_sha256") == spec.sha256, f"{spec.role} actual SHA mismatch"
        )
        require(
            item.get("media_type") == spec.media_type,
            f"{spec.role} media type mismatch",
        )


def _validate_positions(value: Any) -> None:
    positions = require_list(value, "positions")
    expected = _positions_payload()
    require(positions == expected, "position evidence mismatch or arbitrary allocation")
    numbers = [
        require_mapping(item, "position").get("invoice_position_number")
        for item in positions
    ]
    require(numbers == list(range(1, 89)), "position membership must be exact 1..88")
    totals = [
        require_mapping(item, "position").get("approved_position_total_kzt")
        for item in positions
    ]
    require(all(type(total) is int for total in totals), "position total type")
    require(
        sum(cast(int, total) for total in totals) == APPROVED_TOTAL_KZT,
        "line total mismatch",
    )
    for item in positions:
        position = require_mapping(item, "position")
        require(
            position.get("quantity") * position.get("approved_unit_price_kzt")
            == position.get("approved_position_total_kzt"),
            "multiplicity grain mismatch",
        )


def validate_payload(payload: Mapping[str, Any]) -> None:
    try:
        application.predecessor.validate_against_schema(payload, load_schema())
    except application.predecessor.ContractError as exc:
        raise ContractError(str(exc)) from exc
    predecessor = require_mapping(payload.get("predecessor"), "predecessor binding")
    require(
        predecessor == _expected_predecessor_binding(),
        "predecessor binding mismatch",
    )
    _validate_source_bindings(payload.get("source_input_bindings"))
    require(payload.get("price_grain") == PRICE_GRAIN, "price grain mismatch")
    _validate_positions(payload.get("positions"))
    require(
        payload.get("ledger_summary") == _ledger_summary(), "ledger summary mismatch"
    )
    require(
        payload.get("reconciliation")
        == application.predecessor._reconciliation_payload(),
        "reconciliation mismatch",
    )
    require(
        payload.get("technical_composition") == application._technical_composition(),
        "technical composition drift",
    )
    require(payload.get("safety") == SAFETY, "safety boundary mismatch")


def serialize(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _path_identity(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino


def _rollback_publication(
    output: Path,
    staging: Path | None,
    final_link_created: bool,
    staged_identity: tuple[int, int] | None,
) -> list[str]:
    blockers: list[str] = []
    if final_link_created and os.path.lexists(output):
        try:
            if _path_identity(output) == staged_identity:
                output.unlink()
            else:
                blockers.append("foreign final replacement preserved")
        except OSError as exc:
            blockers.append(f"final output cleanup failed: {exc}")
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


def publish_ledger(
    predecessor_path: Path, predecessor_sha256: str, output: Path
) -> PublicationResult:
    require(output.name == OUTPUT_FILENAME, "output filename mismatch")
    require(output.parent != output, "output directory mismatch")
    require(output.parent.parent.is_dir(), "output directory owner must already exist")
    require(not output.parent.exists(), "output directory already exists")
    require(
        not output.resolve(strict=False).is_relative_to(REPO_ROOT),
        "output must be outside repository",
    )
    loaded = load_and_validate_predecessor(predecessor_path, predecessor_sha256)
    require(
        output.resolve(strict=False) != loaded.path, "output must not alias predecessor"
    )
    encoded = serialize(build_payload(loaded))
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
        staged, staged_raw = load_json(staging, "staged commercial pricing ledger")
        require(staged_raw == encoded, "staged bytes mismatch")
        validate_payload(staged)
        require(
            set(output.parent.iterdir()) == {staging},
            "unexpected entry before publication",
        )
        try:
            current = loaded.path.read_bytes()
        except OSError as exc:
            raise ContractError(f"TOCTOU reread failed: predecessor: {exc}") from exc
        require(current == loaded.raw, "TOCTOU bytes changed: predecessor")
        require(
            sha256_bytes(current) == PREDECESSOR_SHA256,
            "TOCTOU SHA mismatch: predecessor",
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
        published, published_raw = load_json(
            output, "published commercial pricing ledger"
        )
        require(published_raw == encoded, "published bytes mismatch")
        validate_payload(published)
        staging.unlink()
        require(
            _path_identity(output) == staged_identity,
            "published final identity changed",
        )
        require(set(output.parent.iterdir()) == {output}, "final inventory mismatch")
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
            _rollback_publication(output, staging, final_link_created, staged_identity)
        )
        if blockers:
            raise ContractError(
                "publication rollback cleanup blocked: " + "; ".join(blockers)
            ) from error
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--price-application", required=True, type=Path)
    parser.add_argument("--price-application-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorization", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    require(
        args.authorization == PUBLICATION_AUTHORIZATION,
        "exact Invoice 519 commercial pricing ledger publication "
        "authorization is required",
    )
    result = publish_ledger(
        cast(Path, args.price_application),
        cast(str, args.price_application_sha256),
        cast(Path, args.output),
    )
    print(
        f"PUBLISHED_IMMUTABLE_NO_OVERWRITE {args.output} "
        f"SHA256={result.sha256} SIZE={result.size}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
