"""Read-only audit of a candidate workbook against the active approved manifest."""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from openpyxl import load_workbook  # type: ignore[import-untyped]
from openpyxl.utils import get_column_letter  # type: ignore[import-untyped]
from price_baseline_contract import (  # type: ignore[import-not-found]
    DEFAULT_ACTIVE_SELECTOR,
    BaselineContractError,
    canonical_json_bytes,
    load_json_bytes,
    resolve_active_price_baseline,
    sha256_bytes,
    sha256_file,
    validate_manifest,
)

AUDIT_SCHEMA = "price_baseline_candidate_audit.v0.1"
MAX_SCAN_ROW = 200


class CandidateAuditError(RuntimeError):
    """The candidate cannot be audited safely."""


@dataclass(frozen=True)
class WorkbookInspection:
    sheet_order: tuple[str, ...]
    price_names: tuple[dict[str, Any], ...]
    formula_cells: tuple[str, ...]
    invalid_price_cells: tuple[str, ...]
    duplicate_names: tuple[str, ...]
    structural_fingerprint: str


def normalize_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.replace("\xa0", " ").split())
    return normalized or None


def positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value > 0 and value.is_integer() else None
    return None


def inspected_price_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return {"type": type(value).__name__, "text": str(value)}


def inspect_workbook(path: Path) -> WorkbookInspection:
    try:
        workbook = load_workbook(
            path,
            read_only=True,
            data_only=False,
            keep_links=False,
        )
    except (OSError, ValueError) as exc:
        raise CandidateAuditError("candidate workbook could not be opened") from exc
    names: list[dict[str, Any]] = []
    formulas: list[str] = []
    invalid_prices: list[str] = []
    duplicates: list[str] = []
    try:
        sheet_order = tuple(workbook.sheetnames)
        for worksheet in workbook.worksheets:
            for row in range(1, MAX_SCAN_ROW + 1):
                for kind, label_column, price_columns in (
                    ("component", 1, (2, 3)),
                    ("cabinet", 12, (13,)),
                ):
                    raw_label = worksheet.cell(row, label_column).value
                    label = normalize_label(raw_label)
                    raw_prices = [
                        worksheet.cell(row, column).value for column in price_columns
                    ]
                    if label is None or not any(
                        value is not None for value in raw_prices
                    ):
                        continue
                    cells = [
                        f"{worksheet.title}!{get_column_letter(column)}{row}"
                        for column in price_columns
                    ]
                    formulas.extend(
                        cell
                        for cell, value in zip(cells, raw_prices, strict=True)
                        if isinstance(value, str) and value.startswith("=")
                    )
                    for cell, value in zip(cells, raw_prices, strict=True):
                        if isinstance(value, str) and value.startswith("="):
                            continue
                        if positive_int(value) is None:
                            rendered = json.dumps(
                                inspected_price_value(value),
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            )
                            invalid_prices.append(
                                f"{cell}: required positive integer literal price "
                                f"is missing or invalid: {rendered}"
                            )
                    names.append(
                        {
                            "kind": kind,
                            "sheet": worksheet.title,
                            "row": row,
                            "label": label,
                            "label_cell": (
                                f"{worksheet.title}!"
                                f"{get_column_letter(label_column)}{row}"
                            ),
                            "price_cells": cells,
                            "price_values": {
                                cell: inspected_price_value(value)
                                for cell, value in zip(cells, raw_prices, strict=True)
                            },
                        }
                    )
        counts = Counter(
            (entry["kind"], entry["sheet"], entry["label"]) for entry in names
        )
        duplicates = [
            f"{kind}:{sheet}:{label}"
            for (kind, sheet, label), count in sorted(counts.items())
            if count > 1
        ]
        structural_payload = {
            "sheet_order": list(sheet_order),
            "price_name_coordinates": [
                {
                    "kind": entry["kind"],
                    "sheet": entry["sheet"],
                    "row": entry["row"],
                    "label": entry["label"],
                    "label_cell": entry["label_cell"],
                    "price_cells": entry["price_cells"],
                }
                for entry in names
            ],
        }
        fingerprint = sha256_bytes(canonical_json_bytes(structural_payload))
        return WorkbookInspection(
            sheet_order=sheet_order,
            price_names=tuple(names),
            formula_cells=tuple(sorted(formulas)),
            invalid_price_cells=tuple(sorted(invalid_prices)),
            duplicate_names=tuple(duplicates),
            structural_fingerprint=fingerprint,
        )
    finally:
        workbook.close()


def _price_row_key(entry: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        entry["kind"],
        entry["sheet"],
        entry["row"],
        entry["label"],
        entry["label_cell"],
        tuple(cast(list[str], entry["price_cells"])),
    )


def _governed_sources(
    snapshot: Sequence[Mapping[str, Any]],
) -> dict[tuple[Any, ...], list[str]]:
    governed: dict[tuple[Any, ...], list[str]] = {}
    for entry in snapshot:
        source = cast(Mapping[str, Any], entry["source"])
        mapping_kind = cast(str, entry["mapping_kind"])
        expected_label = normalize_label(
            cast(Mapping[str, Any], entry["identity"])["expected_label"]
        )
        key = (
            mapping_kind.split("_", maxsplit=1)[0],
            source["sheet"],
            source["row"],
            expected_label,
            source["label_cell"],
            tuple(cast(list[str], source["price_cells"])),
        )
        governed.setdefault(key, []).append(cast(str, entry["mapping_id"]))
    return {key: sorted(values) for key, values in governed.items()}


def diff_all_price_values(
    predecessor: WorkbookInspection,
    candidate: WorkbookInspection,
    governed_snapshot: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    candidate_by_key = {_price_row_key(entry): entry for entry in candidate.price_names}
    governed = _governed_sources(governed_snapshot)
    changes: list[dict[str, Any]] = []
    for predecessor_entry in predecessor.price_names:
        key = _price_row_key(predecessor_entry)
        candidate_entry = candidate_by_key.get(key)
        if candidate_entry is None:
            continue
        before = cast(Mapping[str, Any], predecessor_entry["price_values"])
        after = cast(Mapping[str, Any], candidate_entry["price_values"])
        if dict(before) == dict(after):
            continue
        mapping_ids = governed.get(key, [])
        changes.append(
            {
                "kind": predecessor_entry["kind"],
                "sheet": predecessor_entry["sheet"],
                "row": predecessor_entry["row"],
                "label": predecessor_entry["label"],
                "label_cell": predecessor_entry["label_cell"],
                "price_cells": predecessor_entry["price_cells"],
                "before": dict(before),
                "after": dict(after),
                "currently_governed": bool(mapping_ids),
                "governed_mapping_ids": mapping_ids,
            }
        )
    return changes


def _manifest_data(path: Path) -> Mapping[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CandidateAuditError("active manifest could not be reread") from exc
    data = cast(Mapping[str, Any], load_json_bytes(raw, "active manifest"))
    validate_manifest(data)
    return data


def _entry_prices(
    workbook: Any,
    entry: Mapping[str, Any],
    conflicts: dict[str, list[str]],
) -> dict[str, int] | None:
    source = cast(Mapping[str, Any], entry["source"])
    identity = cast(Mapping[str, Any], entry["identity"])
    sheet_name = cast(str, source["sheet"])
    try:
        worksheet = workbook[sheet_name]
    except KeyError:
        conflicts["missing"].append(f"missing worksheet: {sheet_name}")
        return None
    label_cell = cast(str, source["label_cell"]).split("!", maxsplit=1)[-1]
    actual_raw_label = worksheet[label_cell].value
    expected_label = identity.get("expected_label")
    strict_label = identity.get("strict_label") is True
    actual_label = (
        actual_raw_label if strict_label else normalize_label(actual_raw_label)
    )
    expected = expected_label if strict_label else normalize_label(expected_label)
    if actual_label != expected:
        conflicts["mapping_identity_drift"].append(
            f"{entry['mapping_id']}: label/source identity changed at "
            f"{sheet_name}!{label_cell}"
        )
        return None
    price_cells = cast(list[str], source["price_cells"])
    values: list[int] = []
    for coordinate in price_cells:
        cell = coordinate.split("!", maxsplit=1)[-1]
        raw_value = worksheet[cell].value
        if isinstance(raw_value, str) and raw_value.startswith("="):
            conflicts["formula"].append(coordinate)
            return None
        parsed = positive_int(raw_value)
        if parsed is None:
            conflicts["missing"].append(
                f"{entry['mapping_id']}: invalid or missing price at {coordinate}"
            )
            return None
        values.append(parsed)
    if cast(str, entry["mapping_kind"]).startswith("component_"):
        if len(values) != 2:
            conflicts["missing"].append(
                f"{entry['mapping_id']}: component requires material and work prices"
            )
            return None
        return {"material_kzt": values[0], "work_kzt": values[1]}
    if len(values) != 1:
        conflicts["missing"].append(
            f"{entry['mapping_id']}: cabinet requires one price"
        )
        return None
    return {"price_kzt": values[0]}


def audit_candidate(
    selector_path: Path,
    candidate_workbook: Path,
) -> dict[str, Any]:
    selector_file = selector_path.resolve(strict=False)
    candidate_file = candidate_workbook.resolve(strict=False)
    if (
        not candidate_file.is_relative_to(selector_file.parent)
        or candidate_file.suffix.casefold() != ".xlsx"
    ):
        raise CandidateAuditError("candidate workbook is outside canonical price root")
    selector_before = selector_file.read_bytes() if selector_file.is_file() else b""
    try:
        active = resolve_active_price_baseline(selector_file)
    except (BaselineContractError, OSError) as exc:
        raise CandidateAuditError(f"active baseline is invalid: {exc}") from exc
    if active.manifest_path is None or active.manifest_sha256 is None:
        raise CandidateAuditError("active baseline has no manifest provenance")
    predecessor = _manifest_data(active.manifest_path)
    predecessor_workbook = cast(Mapping[str, Any], predecessor["workbook"])
    predecessor_snapshot = list(active.mapping_snapshot)

    try:
        candidate_sha_before = sha256_file(candidate_file)
    except OSError as exc:
        raise CandidateAuditError("candidate workbook could not be read") from exc
    inspection = inspect_workbook(candidate_file)
    predecessor_inspection = inspect_workbook(active.path)
    conflicts: dict[str, list[str]] = {
        "formula": list(inspection.formula_cells),
        "missing": list(inspection.invalid_price_cells),
        "duplicate": list(inspection.duplicate_names),
        "mapping_identity_drift": [],
    }
    candidate_snapshot: list[dict[str, Any]] = []
    workbook: Any | None = None
    try:
        workbook = load_workbook(
            candidate_file,
            read_only=True,
            data_only=False,
            keep_links=False,
        )
        for raw_entry in predecessor_snapshot:
            entry = copy.deepcopy(dict(raw_entry))
            prices = _entry_prices(workbook, entry, conflicts)
            if prices is None:
                continue
            entry["prices"] = prices
            candidate_snapshot.append(entry)
    finally:
        if workbook is not None:
            workbook.close()

    predecessor_names = {
        (entry["kind"], entry["sheet"], entry["label"])
        for entry in predecessor_inspection.price_names
    }
    candidate_names = {
        (entry["kind"], entry["sheet"], entry["label"])
        for entry in inspection.price_names
    }
    added_names = [list(value) for value in sorted(candidate_names - predecessor_names)]
    removed_names = [
        list(value) for value in sorted(predecessor_names - candidate_names)
    ]
    changed_prices = diff_all_price_values(
        predecessor_inspection,
        inspection,
        predecessor_snapshot,
    )
    structural_compatible = (
        inspection.structural_fingerprint
        == predecessor_workbook["structural_fingerprint"]
    )
    hold_reasons: list[str] = []
    if not structural_compatible:
        hold_reasons.append("workbook structural fingerprint changed")
    if added_names or removed_names:
        hold_reasons.append("price-bearing names were added or removed")
    if len(candidate_snapshot) != len(predecessor_snapshot):
        hold_reasons.append("governed mapping snapshot is incomplete")
    for category, findings in conflicts.items():
        if findings:
            hold_reasons.append(f"{category} conflicts detected")

    manifest_id = f"PBM-{candidate_sha_before[:16].upper()}"
    approval_payload = {
        "manifest_id": manifest_id,
        "predecessor_manifest_id": active.manifest_id,
        "predecessor_manifest_sha256": active.manifest_sha256,
        "candidate_workbook_path": str(candidate_file),
        "candidate_workbook_sha256": candidate_sha_before,
        "candidate_structural_fingerprint": inspection.structural_fingerprint,
        "mapping_snapshot_sha256": sha256_bytes(
            canonical_json_bytes(candidate_snapshot)
        ),
        "future_cases_only": True,
        "historical_repricing_authorized": False,
    }
    approval_fingerprint = sha256_bytes(canonical_json_bytes(approval_payload))
    audit = {
        "schema_version": AUDIT_SCHEMA,
        "status": "PASS_CANDIDATE_ONLY" if not hold_reasons else "HOLD",
        "manifest_id": manifest_id,
        "predecessor": {
            "manifest_id": active.manifest_id,
            "manifest_path": str(active.manifest_path),
            "manifest_sha256": active.manifest_sha256,
        },
        "candidate_workbook": {
            "path": str(candidate_file),
            "sha256": candidate_sha_before,
            "structural_fingerprint": inspection.structural_fingerprint,
        },
        "structural_compatibility": structural_compatible,
        "changed_prices": changed_prices,
        "added_names": added_names,
        "removed_names": removed_names,
        "conflicts": conflicts,
        "mapping_snapshot": candidate_snapshot,
        "hold_reasons": hold_reasons,
        "approval_payload": approval_payload,
        "approval_fingerprint": approval_fingerprint,
    }
    if sha256_file(candidate_file) != candidate_sha_before:
        raise CandidateAuditError("candidate workbook changed during audit")
    if selector_file.read_bytes() != selector_before:
        raise CandidateAuditError("active selector changed during audit")
    if sha256_file(active.manifest_path) != active.manifest_sha256:
        raise CandidateAuditError("active manifest changed during audit")
    return audit


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--active-selector",
        type=Path,
        default=DEFAULT_ACTIVE_SELECTOR,
    )
    parser.add_argument("--candidate-workbook", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        audit = audit_candidate(args.active_selector, args.candidate_workbook)
    except (CandidateAuditError, OSError) as exc:
        print(f"AUDIT HOLD: {exc}")
        return 1
    print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if audit["status"] == "PASS_CANDIDATE_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
