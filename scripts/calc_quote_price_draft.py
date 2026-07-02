"""Calculate a read-only preliminary price draft from confirmed composition CSV."""

from __future__ import annotations

import argparse
import csv
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook  # type: ignore[import-untyped]

CSV_DELIMITER = ";"
KRN_SHEET_NAME = "КРН"
MAX_LOOKUP_ROW = 200
REQUIRED_COLUMNS = (
    "product_name",
    "cabinet_code",
    "consumables_factor",
    "component_code",
    "component_qty",
    "install_type",
)
POSITIVE_INTEGER_RE = re.compile(r"[1-9][0-9]*\Z")
POSITIVE_DECIMAL_RE = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
MATERIAL_MULTIPLIER = Decimal("1.25")
FINAL_MULTIPLIER = Decimal("1.15")


@dataclass(frozen=True)
class ComponentDefinition:
    workbook_label: str
    install_type: str


COMPONENT_DEFINITIONS = {
    "EKF-VA47-29-1P": ComponentDefinition(
        workbook_label="ВА47 1 полюсный",
        install_type="modular_1p",
    ),
    "EKF-VA47-29-3P": ComponentDefinition(
        workbook_label="ВА47 3 полюсный до 63А",
        install_type="modular_3p",
    ),
    "EKF-RN-47": ComponentDefinition(
        workbook_label="независимый расцепитель для ВА47 РН47",
        install_type="modular_1p",
    ),
}
CABINET_DEFINITIONS = {
    "CAB-KRN-24": "Корпус КРН-24 395х330х100",
}


@dataclass(frozen=True)
class CompositionRow:
    product_name: str
    cabinet_code: str
    consumables_factor: Decimal
    component_code: str
    component_qty: int
    install_type: str


@dataclass
class PriceCalculationResult:
    price_workbook: Path
    input_csv: Path
    status: str = "FAIL"
    product_name: str | None = None
    input_rows_count: int = 0
    cabinet_code: str | None = None
    cabinet_label: str | None = None
    cabinet_price: int | None = None
    component_material_total: int | None = None
    work_total: int | None = None
    consumables_factor: Decimal | None = None
    base: Decimal | None = None
    total_preliminary_price: int | None = None
    red_flags: list[str] = field(default_factory=list)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate a read-only preliminary price draft from confirmed "
            "composition CSV using only the КРН worksheet."
        )
    )
    parser.add_argument(
        "--price-workbook",
        required=True,
        type=Path,
        help="Path to the approved .xlsx price workbook",
    )
    parser.add_argument(
        "--input-csv",
        required=True,
        type=Path,
        help="Path to confirmed semicolon-delimited composition CSV",
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


def load_composition_rows(result: PriceCalculationResult) -> list[CompositionRow]:
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
    if tuple(header) != REQUIRED_COLUMNS:
        add_red_flag(
            result,
            "input header must exactly match the confirmed composition contract",
        )
        return []
    if not raw_rows:
        add_red_flag(result, "input composition CSV must contain at least one row")
        return []

    rows: list[CompositionRow] = []
    for row_number, values in enumerate(raw_rows, start=2):
        if len(values) != len(REQUIRED_COLUMNS):
            add_red_flag(result, f"row {row_number}: field count mismatch")
            continue

        row = dict(zip(REQUIRED_COLUMNS, values, strict=True))
        empty_columns = [
            column for column in REQUIRED_COLUMNS if row[column].strip() == ""
        ]
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

        component_code = row["component_code"]
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

        cabinet_code = row["cabinet_code"]
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
    result.cabinet_label = CABINET_DEFINITIONS[rows[0].cabinet_code]
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


def read_component_prices(
    worksheet: Any,
    required_codes: set[str],
    result: PriceCalculationResult,
) -> dict[str, tuple[int, int]]:
    label_to_code = {
        normalize_workbook_label(definition.workbook_label): code
        for code, definition in COMPONENT_DEFINITIONS.items()
        if code in required_codes
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
                f"cabinet price row was not found in КРН for "
                f"{cabinet_code}; ask Igor",
            )
        return None
    if len(found_prices) > 1:
        add_red_flag(
            result,
            f"duplicate cabinet price row in КРН for {cabinet_code}; ask Igor",
        )
        return None
    return found_prices[0]


def calculate_price_draft(
    price_workbook: Path,
    input_csv: Path,
) -> PriceCalculationResult:
    result = PriceCalculationResult(
        price_workbook=resolved(price_workbook),
        input_csv=resolved(input_csv),
    )
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
        try:
            worksheet = workbook[KRN_SHEET_NAME]
        except KeyError:
            add_red_flag(result, "required worksheet КРН was not found; ask Igor")
            return result

        required_codes = {row.component_code for row in rows}
        component_prices = read_component_prices(
            worksheet,
            required_codes,
            result,
        )
        cabinet_price = read_cabinet_price(
            worksheet,
            rows[0].cabinet_code,
            result,
        )
    except OSError, ValueError:
        add_red_flag(result, "price workbook could not be opened safely")
        return result
    finally:
        if workbook is not None:
            workbook.close()

    if result.red_flags or cabinet_price is None:
        return result

    material_total = sum(
        component_prices[row.component_code][0] * row.component_qty for row in rows
    )
    work_total = sum(
        component_prices[row.component_code][1] * row.component_qty for row in rows
    )
    factor = rows[0].consumables_factor
    base = (
        Decimal(cabinet_price) + Decimal(material_total) * factor + Decimal(work_total)
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
    result = calculate_price_draft(args.price_workbook, args.input_csv)
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
