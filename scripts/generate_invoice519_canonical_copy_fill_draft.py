"""Generate one local Invoice 519 draft by patching the canonical XLSX copy."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn, cast
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PUBLISHER_PATH = Path(__file__).with_name(
    "publish_invoice519_commercial_pricing_ledger.py"
)
YAUO_PUBLISHER_PATH = Path(__file__).with_name(
    "publish_invoice519_yauo_enclosure_human_decision.py"
)
INSPECTOR_PATH = Path(__file__).with_name("inspect_excel_template.py")
PATCHER_PATH = Path(__file__).with_name("ooxml_cell_patcher.py")

LEDGER_PATH = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-"
    "INVOICE519-COMMERCIAL-PRICING-LEDGER-20260828-001\\"
    "invoice519-commercial-pricing-ledger-v0.1.json"
)
LEDGER_SHA256 = "3391f456ff9a01eed59b455549127a73e46aa97b0f4607c291759b5753959fdc"
YAUO_DECISION_PATH = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-"
    "INVOICE519-YAUO-ENCLOSURE-HUMAN-DECISION-20260831-001\\"
    "invoice519-yauo-enclosure-human-decision-v0.1.json"
)
YAUO_DECISION_SHA256 = (
    "214a9114c5b676f3754f3220cfe5b3488d9c4ce75325f98072b7e8e9a5f29717"
)
CANONICAL_WORKBOOK_PATH = Path(
    r"C:\Users\IgorN\Downloads\2026.06.22_519_ТОО «Sensata Industrial».xlsx"
)
CANONICAL_WORKBOOK_SHA256 = (
    "17e31d0312f728800d31fd4f125d285edb1114880500d4833261239b87ab58b5"
)

OUTPUT_FILENAME = "invoice519-canonical-copy-fill-draft.xlsx"
GENERATION_AUTHORIZATION = (
    "IGOR_INVOICE519_CANONICAL_COPY_FILL_DRAFT_GENERATION_AUTHORIZED"
)
WORKSHEET = "Лист1"
APPROVED_TOTAL_KZT = 19_499_186
APPROVED_LEAD_TIME = "30–40 рабочих дней"
LEAD_TIME_CELL = "G10"
TOTAL_CELL = "I113"
AMOUNT_WORDS_CELL = "C115"
YAUO_CELL = "G111"
CANONICAL_LEAD_TIME_VALUE = "Срок изготовления 30-40 рабочих дней"
APPROVED_LEAD_TIME_VALUE = f"Срок изготовления {APPROVED_LEAD_TIME}"
CANONICAL_YAUO_VALUE = "Накладной 450х300х250 металл 1,2мм"
APPROVED_YAUO_VALUE = "Накладной 400х300х250 металл 1,2мм"
CANONICAL_AMOUNT_WORDS_VALUE = (
    " ВСЕГО: Восемнадцать миллионов девятьсот семьдесят девять тысяч "
    "триста девяносто один тенге, в том числе НДС 0%."
)
APPROVED_AMOUNT_WORDS_VALUE = (
    " ВСЕГО: Девятнадцать миллионов четыреста девяносто девять тысяч "
    "сто восемьдесят шесть тенге, в том числе НДС 0%."
)
CANONICAL_TOTAL_VALUE = "=SUM(I17:I112)"
POSITION_ROWS = (
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    31,
    33,
    34,
    35,
    36,
    37,
    38,
    40,
    41,
    42,
    43,
    44,
    45,
    46,
    47,
    48,
    49,
    50,
    51,
    52,
    53,
    54,
    55,
    56,
    58,
    59,
    60,
    61,
    62,
    63,
    65,
    66,
    67,
    68,
    69,
    70,
    71,
    72,
    73,
    74,
    75,
    76,
    77,
    78,
    80,
    81,
    82,
    83,
    84,
    85,
    87,
    88,
    89,
    90,
    91,
    92,
    93,
    94,
    95,
    96,
    97,
    98,
    99,
    100,
    101,
    102,
    104,
    105,
    106,
    107,
    108,
    109,
    111,
    112,
)
SECTION_ROWS = (32, 39, 57, 64, 79, 86, 103, 110)


class GeneratorError(ValueError):
    """The requested draft generation would violate the closed contract."""


@dataclass(frozen=True)
class LoadedJson:
    path: Path
    raw: bytes
    payload: dict[str, Any]


@dataclass(frozen=True)
class LoadedCanonical:
    path: Path
    raw: bytes
    parts: dict[str, bytes]
    worksheet_part: str
    worksheet_xml: bytes
    cell_values: dict[str, str | None]
    cell_styles: dict[str, str | None]


@dataclass(frozen=True)
class LinePrice:
    position: int
    row: int
    quantity: int
    unit_price_kzt: int
    position_total_kzt: int


@dataclass(frozen=True)
class GenerationResult:
    output: Path
    sha256: str
    size: int
    modified_cells: tuple[str, ...]


def fail(message: str) -> NoReturn:
    raise GeneratorError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def load_sibling_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"required sibling module is missing: {path.name}")
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ledger_publisher = load_sibling_module(
    "invoice519_commercial_pricing_ledger_for_copy_fill", LEDGER_PUBLISHER_PATH
)
yauo_publisher = load_sibling_module(
    "invoice519_yauo_decision_for_copy_fill", YAUO_PUBLISHER_PATH
)
inspector = load_sibling_module(
    "invoice519_template_inspector_for_copy_fill", INSPECTOR_PATH
)
patcher = load_sibling_module("invoice519_ooxml_patcher_for_copy_fill", PATCHER_PATH)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def read_exact_bytes(
    path: Path, expected_path: Path, expected_sha: str, label: str
) -> tuple[Path, bytes]:
    try:
        actual_path = path.resolve(strict=True)
    except OSError as exc:
        raise GeneratorError(f"{label} path unavailable: {exc}") from exc
    require(actual_path == resolved(expected_path), f"{label} path binding mismatch")
    try:
        raw = actual_path.read_bytes()
    except OSError as exc:
        raise GeneratorError(f"{label} could not be read: {exc}") from exc
    require(sha256_bytes(raw) == expected_sha, f"{label} SHA-256 mismatch")
    return actual_path, raw


def load_bound_json(
    path: Path,
    expected_path: Path,
    expected_sha: str,
    label: str,
    validator: Any,
) -> LoadedJson:
    actual_path, raw = read_exact_bytes(path, expected_path, expected_sha, label)
    try:
        text = raw.decode("utf-8", errors="strict")
        payload = json.loads(text, object_pairs_hook=reject_duplicate_keys)
        require(isinstance(payload, Mapping), f"{label} root must be an object")
        validator(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise GeneratorError(f"{label} strict contract failed: {exc}") from exc
    return LoadedJson(actual_path, raw, dict(payload))


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def mapping(value: Any, label: str) -> Mapping[str, Any]:
    require(isinstance(value, Mapping), f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def exact_int(value: Any, label: str) -> int:
    require(type(value) is int, f"{label} must be an integer")
    return cast(int, value)


def load_ledger(path: Path, expected_sha: str) -> LoadedJson:
    loaded = load_bound_json(
        path,
        LEDGER_PATH,
        expected_sha,
        "commercial pricing ledger",
        ledger_publisher.validate_payload,
    )
    require(expected_sha == LEDGER_SHA256, "ledger SHA argument binding mismatch")
    validate_ledger_payload(loaded.payload)
    return loaded


def validate_ledger_payload(payload: Mapping[str, Any]) -> None:
    require(
        payload.get("schema_version") == "invoice519_commercial_pricing_ledger.v0.1",
        "ledger schema version mismatch",
    )
    require(
        payload.get("status")
        == "IGOR_INVOICE519_88_POSITION_PRICING_LEDGER_READY_QUOTE_NOT_GENERATED",
        "ledger status mismatch",
    )
    require(payload.get("application_status") == "APPLIED", "ledger not APPLIED")
    summary = mapping(payload.get("ledger_summary"), "ledger summary")
    expected_summary = {
        "position_count": 88,
        "approved_total_kzt": APPROVED_TOTAL_KZT,
        "derived_line_total_kzt": APPROVED_TOTAL_KZT,
        "frozen_55_subtotal_kzt": 11_963_792,
        "checked_missing_33_subtotal_kzt": 7_535_394,
        "duplicates": 0,
        "missing": 0,
        "extra": 0,
        "unit_price_allocation_used": False,
        "price_recalculation_used": False,
        "technical_composition_changed": False,
    }
    for key, expected in expected_summary.items():
        require(summary.get(key) == expected, f"ledger summary mismatch: {key}")
    reconciliation = mapping(payload.get("reconciliation"), "ledger reconciliation")
    coverage = mapping(reconciliation.get("coverage"), "ledger coverage")
    require(
        coverage == {"covered": 88, "total": 88, "overlap": 0, "uncovered": 0},
        "ledger reconciliation coverage mismatch",
    )
    require(
        reconciliation.get("combined_total_kzt") == APPROVED_TOTAL_KZT,
        "ledger reconciliation total mismatch",
    )
    require(
        reconciliation.get("frozen_55_recalculated") is False,
        "ledger frozen 55 recalculation mismatch",
    )
    price_grain = mapping(payload.get("price_grain"), "ledger price grain")
    require(
        price_grain.get("unit_prices_recalculated") is False
        and price_grain.get("arbitrary_allocation_used") is False,
        "ledger price calculation boundary mismatch",
    )
    technical = mapping(
        payload.get("technical_composition"), "ledger technical composition"
    )
    require(
        technical.get("status") == "UNCHANGED_FROM_PREDECESSOR",
        "ledger technical composition changed",
    )
    safety = mapping(payload.get("safety"), "ledger safety")
    for key in (
        "quote_generation_authorized",
        "invoice_generation_authorized",
        "quote_or_invoice_publication_authorized",
        "client_send_authorized",
        "procurement_authorized",
        "reserve_authorized",
        "prepayment_authorized",
        "production_authorized",
        "downstream_authorized",
    ):
        require(safety.get(key) is False, f"ledger safety boundary open: {key}")


def ledger_lines(payload: Mapping[str, Any]) -> tuple[LinePrice, ...]:
    positions = payload.get("positions")
    require(isinstance(positions, list), "ledger positions must be an array")
    require(len(positions) == 88, "ledger positions count mismatch")
    result: list[LinePrice] = []
    for item_value in positions:
        item = mapping(item_value, "ledger position")
        number = exact_int(item.get("invoice_position_number"), "invoice position")
        quantity = exact_int(item.get("quantity"), f"position {number} quantity")
        unit_price = exact_int(
            item.get("approved_unit_price_kzt"), f"position {number} unit price"
        )
        total = exact_int(
            item.get("approved_position_total_kzt"), f"position {number} total"
        )
        require(
            quantity > 0 and unit_price > 0 and total > 0,
            f"position {number} price values",
        )
        require(
            total == quantity * unit_price, f"position {number} multiplicity mismatch"
        )
        provenance = mapping(
            item.get("pricing_provenance"), f"position {number} provenance"
        )
        require(
            provenance.get("price_recalculated") is False,
            f"position {number} was recalculated",
        )
        require(
            provenance.get("allocation_method")
            in {
                "DIRECT_CHECKED_POSITION_PRICE",
                "DIRECT_CHECKED_FAMILY_POSITION_PRICE",
            },
            f"position {number} arbitrary allocation",
        )
        reference = mapping(
            item.get("technical_description_reference"),
            f"position {number} technical reference",
        )
        require(
            reference.get("source_binding_role") == "canonical_invoice_519"
            and reference.get("worksheet") == WORKSHEET
            and reference.get("composition_status")
            == "UNCHANGED_FROM_PRICE_APPLICATION_PREDECESSOR",
            f"position {number} technical reference mismatch",
        )
        row = exact_int(reference.get("row"), f"position {number} row")
        result.append(LinePrice(number, row, quantity, unit_price, total))
    require(
        tuple(line.position for line in result) == tuple(range(1, 89)),
        "ledger position membership/order mismatch",
    )
    require(
        tuple(line.row for line in result) == POSITION_ROWS,
        "ledger canonical row mapping mismatch",
    )
    require(
        sum(line.position_total_kzt for line in result) == APPROVED_TOTAL_KZT,
        "ledger derived total mismatch",
    )
    return tuple(result)


def load_yauo_decision(path: Path, expected_sha: str) -> LoadedJson:
    loaded = load_bound_json(
        path,
        YAUO_DECISION_PATH,
        expected_sha,
        "YAUO enclosure Human Decision",
        yauo_publisher.validate_payload,
    )
    require(expected_sha == YAUO_DECISION_SHA256, "YAUO SHA argument binding mismatch")
    payload = loaded.payload
    require(
        payload.get("schema_version")
        == "invoice519_yauo_enclosure_human_decision.v0.1",
        "YAUO schema version mismatch",
    )
    require(
        payload.get("status")
        == "IGOR_INVOICE519_YAUO_ENCLOSURE_APPROVED_NOT_APPLIED_TO_QUOTE",
        "YAUO status mismatch",
    )
    require(
        payload.get("approval_scope") == "ENCLOSURE_DIMENSIONS_ONLY",
        "YAUO approval scope mismatch",
    )
    require(
        payload.get("quote_application_status") == "NOT_APPLIED",
        "YAUO quote application status mismatch",
    )
    decision = mapping(payload.get("technical_decision"), "YAUO technical decision")
    expected_decision = {
        "invoice_position_number": 87,
        "product_identity": "YAUO9601_3474",
        "field": "enclosure_dimensions",
        "previous_value": "450×300×250 mm",
        "approved_value": "400×300×250 mm",
        "change_scope": "POSITION_87_ENCLOSURE_ONLY",
        "quote_application_status": "NOT_APPLIED",
    }
    require(decision == expected_decision, "YAUO exact decision mismatch")
    safety = mapping(payload.get("safety"), "YAUO safety")
    true_flags = {key for key, value in safety.items() if value is True}
    require(
        true_flags == {"human_decision_recorded", "technical_decision_recorded"},
        "YAUO safety boundary mismatch",
    )
    return loaded


def _zip_parts(raw: bytes, label: str) -> dict[str, bytes]:
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            require(len(names) == len(set(names)), f"{label} has duplicate ZIP members")
            require(archive.testzip() is None, f"{label} ZIP CRC failure")
            return {name: archive.read(name) for name in names}
    except (BadZipFile, OSError) as exc:
        raise GeneratorError(f"{label} is not a valid XLSX package: {exc}") from exc


def _worksheet_values(
    raw: bytes,
) -> tuple[str, bytes, dict[str, str | None], dict[str, str | None]]:
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            sheets = inspector.workbook_sheets(archive)
            matches = [part for name, part in sheets if name == WORKSHEET]
            require(
                len(matches) == 1,
                "canonical authority worksheet binding mismatch",
            )
            worksheet_part = cast(str, matches[0])
            shared_strings = inspector.load_shared_strings(archive)
            root = inspector.read_xml_part(archive, worksheet_part)
            values: dict[str, str | None] = {}
            styles: dict[str, str | None] = {}
            for cell in root.findall(".//main:c", inspector.NS):
                coordinate = cell.get("r")
                if coordinate is None:
                    continue
                require(
                    coordinate not in values, f"duplicate canonical cell: {coordinate}"
                )
                values[coordinate] = inspector.cell_value(cell, shared_strings)
                styles[coordinate] = cell.get("s")
            return worksheet_part, ElementTree.tostring(root), values, styles
    except (BadZipFile, KeyError, ElementTree.ParseError, ValueError) as exc:
        raise GeneratorError(f"canonical workbook inspection failed: {exc}") from exc


def load_canonical(path: Path, expected_sha: str) -> LoadedCanonical:
    require(
        expected_sha == CANONICAL_WORKBOOK_SHA256,
        "canonical SHA argument binding mismatch",
    )
    actual_path, raw = read_exact_bytes(
        path, CANONICAL_WORKBOOK_PATH, expected_sha, "canonical workbook"
    )
    parts = _zip_parts(raw, "canonical workbook")
    worksheet_part, _serialized_root, values, styles = _worksheet_values(raw)
    require(worksheet_part in parts, "canonical worksheet part missing")
    return LoadedCanonical(
        actual_path,
        raw,
        parts,
        worksheet_part,
        parts[worksheet_part],
        values,
        styles,
    )


def validate_canonical_map(
    canonical: LoadedCanonical, lines: Sequence[LinePrice]
) -> None:
    require(len(lines) == 88, "canonical map line count mismatch")
    for line in lines:
        require(
            canonical.cell_values.get(f"B{line.row}") == str(line.position),
            f"canonical position mismatch: {line.position}",
        )
        raw_quantity = canonical.cell_values.get(f"E{line.row}")
        try:
            canonical_quantity = int(cast(str, raw_quantity))
        except (TypeError, ValueError) as exc:
            raise GeneratorError(
                f"canonical quantity invalid: position {line.position}"
            ) from exc
        require(
            canonical_quantity == line.quantity,
            f"canonical quantity mismatch: position {line.position}",
        )
        for column in ("H", "I"):
            require(
                f"{column}{line.row}" in canonical.cell_values,
                f"canonical price cell missing: {column}{line.row}",
            )
    require(
        canonical.cell_values.get(LEAD_TIME_CELL) == CANONICAL_LEAD_TIME_VALUE,
        "canonical lead-time cell mismatch",
    )
    require(
        canonical.cell_values.get(YAUO_CELL) == CANONICAL_YAUO_VALUE,
        "canonical YAUO cell mismatch",
    )
    require(
        canonical.cell_values.get(AMOUNT_WORDS_CELL) == CANONICAL_AMOUNT_WORDS_VALUE,
        "canonical amount-words cell mismatch",
    )
    require(
        canonical.cell_values.get(TOTAL_CELL) == CANONICAL_TOTAL_VALUE,
        "canonical total cell mismatch",
    )
    require(
        tuple(row for row in range(17, 113) if row not in POSITION_ROWS)
        == SECTION_ROWS,
        "canonical section-row map mismatch",
    )


def build_updates(lines: Sequence[LinePrice]) -> dict[str, object]:
    updates: dict[str, object] = {}
    for line in lines:
        updates[f"H{line.row}"] = line.unit_price_kzt
        updates[f"I{line.row}"] = line.position_total_kzt
    updates[TOTAL_CELL] = APPROVED_TOTAL_KZT
    updates[AMOUNT_WORDS_CELL] = APPROVED_AMOUNT_WORDS_VALUE
    updates[LEAD_TIME_CELL] = APPROVED_LEAD_TIME_VALUE
    updates[YAUO_CELL] = APPROVED_YAUO_VALUE
    require(len(updates) == 180, "modified-cell allowlist size mismatch")
    require(
        set(updates)
        == {
            *(f"H{row}" for row in POSITION_ROWS),
            *(f"I{row}" for row in POSITION_ROWS),
            TOTAL_CELL,
            AMOUNT_WORDS_CELL,
            LEAD_TIME_CELL,
            YAUO_CELL,
        },
        "modified-cell allowlist mismatch",
    )
    return updates


def _cell_xml_map(worksheet_xml: bytes) -> dict[str, bytes]:
    ranges = patcher.cell_ranges(worksheet_xml)
    result: dict[str, bytes] = {}
    for coordinate, matches in ranges.items():
        require(len(matches) == 1, f"duplicate worksheet cell: {coordinate}")
        result[coordinate] = cast(bytes, matches[0].xml)
    return result


def expected_patched_worksheet(
    canonical: LoadedCanonical, updates: Mapping[str, object]
) -> bytes:
    try:
        return cast(
            bytes, patcher.patched_worksheet_xml(canonical.worksheet_xml, updates)
        )
    except Exception as exc:
        raise GeneratorError(f"OOXML cell patch plan failed: {exc}") from exc


def _strict_xml_parts(parts: Mapping[str, bytes]) -> None:
    for name, raw in parts.items():
        if name.endswith((".xml", ".rels")):
            try:
                ElementTree.fromstring(raw)
            except ElementTree.ParseError as exc:
                raise GeneratorError(f"output XML part invalid: {name}: {exc}") from exc


def validate_candidate(
    candidate: Path,
    canonical: LoadedCanonical,
    expected_worksheet: bytes,
    updates: Mapping[str, object],
) -> bytes:
    try:
        raw = candidate.read_bytes()
    except OSError as exc:
        raise GeneratorError(f"draft candidate could not be read: {exc}") from exc
    parts = _zip_parts(raw, "draft candidate")
    require(set(parts) == set(canonical.parts), "draft ZIP part membership mismatch")
    for name, content in canonical.parts.items():
        if name != canonical.worksheet_part:
            require(parts[name] == content, f"unexpected draft ZIP part change: {name}")
    actual_worksheet = parts.get(canonical.worksheet_part)
    require(actual_worksheet == expected_worksheet, "draft worksheet patch mismatch")
    _strict_xml_parts(parts)
    before_cells = _cell_xml_map(canonical.worksheet_xml)
    after_cells = _cell_xml_map(cast(bytes, actual_worksheet))
    require(
        set(before_cells) == set(after_cells),
        "draft worksheet cell membership mismatch",
    )
    for coordinate in updates:
        before = ElementTree.fromstring(before_cells[coordinate])
        after = ElementTree.fromstring(after_cells[coordinate])
        require(before.get("s") == after.get("s"), f"cell style changed: {coordinate}")
        require(
            not any(child.tag.endswith("}f") or child.tag == "f" for child in after),
            f"target formula remained: {coordinate}",
        )
    worksheet_part, _root, values, _styles = _worksheet_values(raw)
    require(
        worksheet_part == canonical.worksheet_part, "draft worksheet binding mismatch"
    )
    for coordinate, expected in updates.items():
        require(
            values.get(coordinate) == str(expected),
            f"draft cell value mismatch: {coordinate}",
        )
    return raw


def validate_output_path(output: Path) -> Path:
    output_path = resolved(output)
    require(output_path.name == OUTPUT_FILENAME, "output filename mismatch")
    require(output_path.parent != output_path, "output directory mismatch")
    require(
        output_path.parent.parent.is_dir(), "output directory owner must already exist"
    )
    require(not output_path.parent.exists(), "output directory already exists")
    require(
        not output_path.is_relative_to(resolved(REPO_ROOT)),
        "output must be outside repository",
    )
    require(
        output_path != resolved(CANONICAL_WORKBOOK_PATH),
        "output must not alias canonical workbook",
    )
    return output_path


def verify_inputs_unchanged(inputs: Sequence[tuple[Path, bytes, str]]) -> None:
    for path, expected_raw, label in inputs:
        try:
            current = path.read_bytes()
        except OSError as exc:
            raise GeneratorError(f"TOCTOU reread failed: {label}: {exc}") from exc
        require(current == expected_raw, f"TOCTOU bytes changed: {label}")


def _path_identity(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino


def _rollback(
    output: Path,
    staging: Path | None,
    final_created: bool,
    staged_identity: tuple[int, int] | None,
) -> list[str]:
    blockers: list[str] = []
    if final_created and os.path.lexists(output):
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


def generate_draft(
    *,
    ledger_path: Path,
    ledger_sha256: str,
    yauo_decision_path: Path,
    yauo_decision_sha256: str,
    canonical_workbook: Path,
    canonical_workbook_sha256: str,
    output: Path,
) -> GenerationResult:
    output_path = validate_output_path(output)
    ledger = load_ledger(ledger_path, ledger_sha256)
    lines = ledger_lines(ledger.payload)
    yauo = load_yauo_decision(yauo_decision_path, yauo_decision_sha256)
    canonical = load_canonical(canonical_workbook, canonical_workbook_sha256)
    validate_canonical_map(canonical, lines)
    updates = build_updates(lines)
    expected_worksheet = expected_patched_worksheet(canonical, updates)
    inputs = (
        (ledger.path, ledger.raw, "commercial pricing ledger"),
        (yauo.path, yauo.raw, "YAUO enclosure Human Decision"),
        (canonical.path, canonical.raw, "canonical workbook"),
    )
    verify_inputs_unchanged(inputs)

    output_path.parent.mkdir()
    descriptor = -1
    staging: Path | None = None
    staged_identity: tuple[int, int] | None = None
    final_created = False
    try:
        descriptor, staging_name = tempfile.mkstemp(
            prefix=f".{output_path.name}.",
            suffix=".staging.xlsx",
            dir=output_path.parent,
        )
        os.close(descriptor)
        descriptor = -1
        staging = Path(staging_name)
        patcher.write_patched_package(
            canonical.parts,
            canonical.worksheet_part,
            expected_worksheet,
            staging,
        )
        with staging.open("rb+") as stream:
            os.fsync(stream.fileno())
        staged_raw = validate_candidate(staging, canonical, expected_worksheet, updates)
        require(
            set(output_path.parent.iterdir()) == {staging},
            "output directory contains unexpected entries before generation",
        )
        verify_inputs_unchanged(inputs)
        require(not output_path.exists(), "output appeared before generation")
        staged_identity = _path_identity(staging)
        try:
            os.link(staging, output_path)
        except OSError as exc:
            raise GeneratorError(
                f"atomic no-overwrite generation failed: {exc}"
            ) from exc
        final_created = True
        require(
            _path_identity(output_path) == staged_identity,
            "generated output identity mismatch",
        )
        final_raw = validate_candidate(
            output_path, canonical, expected_worksheet, updates
        )
        require(final_raw == staged_raw, "generated output bytes mismatch")
        staging.unlink()
        staging = None
        require(
            _path_identity(output_path) == staged_identity,
            "generated output identity changed",
        )
        require(
            set(output_path.parent.iterdir()) == {output_path},
            "output directory final inventory mismatch",
        )
        return GenerationResult(
            output=output_path,
            sha256=sha256_bytes(final_raw),
            size=len(final_raw),
            modified_cells=tuple(sorted(updates)),
        )
    except BaseException as error:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        blockers = _rollback(output_path, staging, final_created, staged_identity)
        if blockers:
            raise GeneratorError(
                "generation rollback cleanup blocked: " + "; ".join(blockers)
            ) from error
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commercial-pricing-ledger", required=True, type=Path)
    parser.add_argument("--commercial-pricing-ledger-sha256", required=True)
    parser.add_argument("--yauo-enclosure-human-decision", required=True, type=Path)
    parser.add_argument("--yauo-enclosure-human-decision-sha256", required=True)
    parser.add_argument("--canonical-invoice-519", required=True, type=Path)
    parser.add_argument("--canonical-invoice-519-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorization", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    require(
        args.authorization == GENERATION_AUTHORIZATION,
        "exact Invoice 519 canonical draft generation authorization is required",
    )
    result = generate_draft(
        ledger_path=cast(Path, args.commercial_pricing_ledger),
        ledger_sha256=cast(str, args.commercial_pricing_ledger_sha256),
        yauo_decision_path=cast(Path, args.yauo_enclosure_human_decision),
        yauo_decision_sha256=cast(str, args.yauo_enclosure_human_decision_sha256),
        canonical_workbook=cast(Path, args.canonical_invoice_519),
        canonical_workbook_sha256=cast(str, args.canonical_invoice_519_sha256),
        output=cast(Path, args.output),
    )
    print(
        f"GENERATED_LOCAL_DRAFT_IMMUTABLE_NO_OVERWRITE {result.output} "
        f"SHA256={result.sha256} SIZE={result.size} "
        f"MODIFIED_CELLS={len(result.modified_cells)} CLIENT_SEND=CLOSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
