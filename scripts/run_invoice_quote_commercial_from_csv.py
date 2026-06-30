"""Create a reconciled internal commercial quote draft from strict CSV."""

from __future__ import annotations

import argparse
import copy
import csv
import importlib.util
import re
import sys
import uuid
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn, cast
from xml.etree import ElementTree

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMERCIAL_PREFLIGHT_SCRIPT = (
    PROJECT_ROOT / "scripts" / "preflight_quote_commercial_input.py"
)
COMMERCIAL_RECONCILIATION_SCRIPT = (
    PROJECT_ROOT / "scripts" / "inspect_quote_commercial_reconciliation.py"
)
OOXML_CELL_PATCHER_SCRIPT = PROJECT_ROOT / "scripts" / "ooxml_cell_patcher.py"

SHEET_NAME = "Счёт-КП шаблон"
STYLES_PART = "xl/styles.xml"
CERTIFIED_CAPACITY = 100
ITEM_START_ROW = 17
ITEM_END_ROW = 116
TOTAL_ROW = 117
AMOUNT_WORDS_ROW = 119
NUMBER_FORMAT_ID = "3"
NUMBER_FORMAT_CODE = "#,##0"
BASE_ITEM_ROW_HEIGHT = 24
ITEM_ROW_VISUAL_LINE_HEIGHT = 15
ITEM_ROW_VERTICAL_PADDING = 6
MAX_ITEM_ROW_HEIGHT = 360
CELL_STYLE_RE = re.compile(rb'\s+s=(["\'])(?:(?!\1).)*\1')
COUNT_ATTR_RE = re.compile(rb'\s+count=(["\'])[0-9]+\1')
CELL_XFS_CONTAINER_RE = re.compile(
    rb"<(?P<prefix>(?:[A-Za-z_][A-Za-z0-9_.-]*:)?)cellXfs\b"
    rb"(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=prefix)cellXfs\s*>",
    re.DOTALL,
)
ROW_HEIGHT_TEXT_WIDTHS = {
    "name": 28,
    "instruments_and_devices": 35,
    "cabinet_type_dimensions_material": 24,
}
ONES_MASCULINE = (
    "",
    "один",
    "два",
    "три",
    "четыре",
    "пять",
    "шесть",
    "семь",
    "восемь",
    "девять",
)
ONES_FEMININE = (
    "",
    "одна",
    "две",
    "три",
    "четыре",
    "пять",
    "шесть",
    "семь",
    "восемь",
    "девять",
)
TEENS = (
    "десять",
    "одиннадцать",
    "двенадцать",
    "тринадцать",
    "четырнадцать",
    "пятнадцать",
    "шестнадцать",
    "семнадцать",
    "восемнадцать",
    "девятнадцать",
)
TENS = (
    "",
    "",
    "двадцать",
    "тридцать",
    "сорок",
    "пятьдесят",
    "шестьдесят",
    "семьдесят",
    "восемьдесят",
    "девяносто",
)
HUNDREDS = (
    "",
    "сто",
    "двести",
    "триста",
    "четыреста",
    "пятьсот",
    "шестьсот",
    "семьсот",
    "восемьсот",
    "девятьсот",
)
SCALE_FORMS = (
    ("", "", "", False),
    ("тысяча", "тысячи", "тысяч", True),
    ("миллион", "миллиона", "миллионов", False),
    ("миллиард", "миллиарда", "миллиардов", False),
    ("триллион", "триллиона", "триллионов", False),
    ("квадриллион", "квадриллиона", "квадриллионов", False),
)
PASS_NEXT = (
    "retain as an internal draft only; manual Igor check and separate Human "
    "Approval are required"
)
FAIL_NEXT = "no internal draft was published; correct the reported issue and rerun"


class CommercialWriterError(Exception):
    """Expected commercial writer validation or generation failure."""


@dataclass
class CommercialWriterResult:
    commercial_csv: Path
    template: Path
    output: Path
    status: str = "FAIL"
    row_count: int = 0
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "commercial preflight": "fail",
            "capacity100 profile": "fail",
            "output path": "fail",
            "candidate generation": "fail",
            "presentation formatting": "fail",
            "commercial reconciliation": "fail",
            "atomic publish": "fail",
        }
    )
    reconciliation_checks: dict[str, str] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    next_action: str = FAIL_NEXT


def fail(message: str) -> NoReturn:
    raise CommercialWriterError(message)


def load_sibling_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        fail(f"could not load required helper: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


commercial_preflight = cast(
    Any,
    load_sibling_module(
        "preflight_quote_commercial_input_for_writer",
        COMMERCIAL_PREFLIGHT_SCRIPT,
    ),
)
commercial_reconciliation = cast(
    Any,
    load_sibling_module(
        "inspect_quote_commercial_reconciliation_for_writer",
        COMMERCIAL_RECONCILIATION_SCRIPT,
    ),
)
ooxml_cell_patcher = cast(
    Any,
    load_sibling_module(
        "ooxml_cell_patcher_for_commercial_writer",
        OOXML_CELL_PATCHER_SCRIPT,
    ),
)
OoxmlCellPatcherError = ooxml_cell_patcher.OoxmlCellPatcherError
patch_existing_cells = ooxml_cell_patcher.patch_existing_cells
archive_bytes = ooxml_cell_patcher.archive_bytes
cell_ranges = ooxml_cell_patcher.cell_ranges
ensure_non_overlapping_replacements = (
    ooxml_cell_patcher.ensure_non_overlapping_replacements
)
find_markup_end = ooxml_cell_patcher.find_markup_end
worksheet_part_for_sheet = ooxml_cell_patcher.worksheet_part_for_sheet
SPREADSHEET_NS = ooxml_cell_patcher.SPREADSHEET_NS


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a reconciled capacity100 commercial XLSX for internal "
            "draft review only."
        )
    )
    parser.add_argument("--commercial-csv", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--template-capacity", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def validate_generation_paths(
    template: Path,
    output: Path,
    template_capacity: int,
) -> tuple[Path, Path]:
    template_path = resolved(template)
    output_path = resolved(output)

    if template_capacity != CERTIFIED_CAPACITY:
        fail("only the certified capacity100 profile is supported")
    if not template_path.is_file():
        fail(f"template does not exist: {template_path}")
    if template_path.suffix.casefold() != ".xlsx":
        fail("template suffix must be .xlsx")
    if output_path.suffix.casefold() != ".xlsx":
        fail("output suffix must be .xlsx")
    if output_path.exists():
        fail(f"output already exists: {output_path}")
    if not output_path.parent.is_dir():
        fail(f"output parent directory does not exist: {output_path.parent}")
    if is_inside_project(output_path):
        fail(f"output is inside the Git project: {output_path}")
    if template_path == output_path:
        fail("output matches template")
    return template_path, output_path


def load_commercial_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(
                csv_file,
                delimiter=commercial_preflight.CSV_DELIMITER,
                strict=True,
            )
            rows = [dict(row) for row in reader]
    except OSError, UnicodeDecodeError, csv.Error:
        fail("validated commercial CSV could not be read safely")
    if not rows:
        fail("validated commercial CSV contains no rows")
    return rows


def calculate_grand_total(rows: Sequence[Mapping[str, str]]) -> int:
    try:
        return sum(int(row["quantity"]) * int(row["unit_price_kzt"]) for row in rows)
    except KeyError, TypeError, ValueError:
        fail("validated commercial values could not be calculated safely")


def scale_form(value: int, forms: Sequence[str]) -> str:
    last_two = value % 100
    if 11 <= last_two <= 14:
        return forms[2]
    last_digit = value % 10
    if last_digit == 1:
        return forms[0]
    if 2 <= last_digit <= 4:
        return forms[1]
    return forms[2]


def triad_words(value: int, feminine: bool) -> list[str]:
    words: list[str] = []
    hundreds = value // 100
    remainder = value % 100
    if hundreds:
        words.append(HUNDREDS[hundreds])
    if 10 <= remainder <= 19:
        words.append(TEENS[remainder - 10])
        return words
    tens = remainder // 10
    ones = remainder % 10
    if tens:
        words.append(TENS[tens])
    if ones:
        words.append((ONES_FEMININE if feminine else ONES_MASCULINE)[ones])
    return words


def integer_to_russian_words(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        fail("grand total must be a non-negative integer")
    if value == 0:
        return "ноль"

    triads: list[int] = []
    remaining = value
    while remaining:
        triads.append(remaining % 1000)
        remaining //= 1000
    if len(triads) > len(SCALE_FORMS):
        fail("grand total exceeds the supported Russian wording range")

    words: list[str] = []
    for scale_index in range(len(triads) - 1, -1, -1):
        triad = triads[scale_index]
        if triad == 0:
            continue
        singular, paucal, plural, feminine = SCALE_FORMS[scale_index]
        words.extend(triad_words(triad, feminine))
        if scale_index:
            words.append(scale_form(triad, (singular, paucal, plural)))
    return " ".join(words)


def amount_words_text(grand_total: int) -> str:
    words = integer_to_russian_words(grand_total)
    return f"Всего прописью: {words} тенге 00 тиын"


def visual_line_count(value: str, width: int) -> int:
    return sum(max(1, (len(line) + width - 1) // width) for line in value.split("\n"))


def estimate_item_row_height(row: Mapping[str, str]) -> int:
    visual_lines = max(
        visual_line_count(row[field], width)
        for field, width in ROW_HEIGHT_TEXT_WIDTHS.items()
    )
    if visual_lines <= 1:
        return BASE_ITEM_ROW_HEIGHT
    return min(
        MAX_ITEM_ROW_HEIGHT,
        visual_lines * ITEM_ROW_VISUAL_LINE_HEIGHT + ITEM_ROW_VERTICAL_PADDING,
    )


def build_cell_updates(
    rows: Sequence[Mapping[str, str]],
    amount_text: str,
) -> dict[str, str | int | None]:
    updates: dict[str, str | int | None] = {
        f"C{AMOUNT_WORDS_ROW}": amount_text,
    }
    for offset, item in enumerate(rows):
        excel_row = ITEM_START_ROW + offset
        updates[f"C{excel_row}"] = item["name"]
        updates[f"D{excel_row}"] = item["unit"]
        updates[f"E{excel_row}"] = int(item["quantity"])
        updates[f"F{excel_row}"] = item["instruments_and_devices"]
        updates[f"G{excel_row}"] = item["cabinet_type_dimensions_material"]
        updates[f"H{excel_row}"] = int(item["unit_price_kzt"])

    for excel_row in range(ITEM_START_ROW + len(rows), ITEM_END_ROW + 1):
        for column in "CDEFGH":
            updates[f"{column}{excel_row}"] = None
    return updates


def build_row_hidden_updates(rows: Sequence[Mapping[str, str]]) -> dict[int, bool]:
    first_unused_row = ITEM_START_ROW + len(rows)
    return {
        row: row >= first_unused_row for row in range(ITEM_START_ROW, ITEM_END_ROW + 1)
    }


def build_row_height_updates(rows: Sequence[Mapping[str, str]]) -> dict[int, int]:
    updates = {
        ITEM_START_ROW + offset: estimate_item_row_height(item)
        for offset, item in enumerate(rows)
    }
    updates.update(
        {
            row: BASE_ITEM_ROW_HEIGHT
            for row in range(ITEM_START_ROW + len(rows), ITEM_END_ROW + 1)
        }
    )
    return updates


def candidate_path_for(output: Path) -> Path:
    return output.with_name(f".{output.stem}.{uuid.uuid4().hex}.candidate.xlsx")


def generate_candidate(
    template: Path,
    candidate: Path,
    rows: Sequence[Mapping[str, str]],
    amount_text: str,
) -> None:
    try:
        patch_existing_cells(
            template=template,
            output=candidate,
            sheet_name=SHEET_NAME,
            updates=build_cell_updates(rows, amount_text),
            row_hidden_updates=build_row_hidden_updates(rows),
            row_height_updates=build_row_height_updates(rows),
        )
    except OoxmlCellPatcherError as error:
        fail(f"candidate generation failed: {error}")


def number_format_coordinates() -> tuple[str, ...]:
    return tuple(
        [
            *(f"H{row}" for row in range(ITEM_START_ROW, ITEM_END_ROW + 1)),
            *(f"I{row}" for row in range(ITEM_START_ROW, ITEM_END_ROW + 1)),
            f"I{TOTAL_ROW}",
        ]
    )


def cell_style_id(cell_xml: bytes, coordinate: str) -> int:
    try:
        cell = ElementTree.fromstring(cell_xml)
        style_id = int(cell.get("s", "0"))
    except ElementTree.ParseError, ValueError:
        fail(f"presentation style could not be read for {coordinate}")
    if style_id < 0:
        fail(f"presentation style is invalid for {coordinate}")
    return style_id


def style_cell_xml(cell_xml: bytes, style_id: int) -> bytes:
    start_tag_end = find_markup_end(cell_xml, 0)
    start_tag = cell_xml[:start_tag_end]
    replacement = f' s="{style_id}"'.encode("ascii")
    if CELL_STYLE_RE.search(start_tag):
        styled_start_tag = CELL_STYLE_RE.sub(replacement, start_tag, count=1)
    else:
        closing = b"/>" if start_tag.endswith(b"/>") else b">"
        styled_start_tag = start_tag[: -len(closing)] + replacement + closing
    return styled_start_tag + cell_xml[start_tag_end:]


def styles_with_number_format(
    styles_xml: bytes,
    base_style_ids: set[int],
) -> tuple[bytes, dict[int, int]]:
    try:
        root = ElementTree.fromstring(styles_xml)
    except ElementTree.ParseError:
        fail("presentation styles XML is invalid")
    cell_xfs = root.find(f"{{{SPREADSHEET_NS}}}cellXfs")
    if cell_xfs is None:
        fail("presentation styles cellXfs element is missing")
    xfs = list(cell_xfs.findall(f"{{{SPREADSHEET_NS}}}xf"))
    if cell_xfs.get("count") != str(len(xfs)):
        fail("presentation styles count is inconsistent")

    style_map: dict[int, int] = {}
    cloned_xfs: list[bytes] = []
    next_style_id = len(xfs)
    ElementTree.register_namespace("", SPREADSHEET_NS)
    for base_style_id in sorted(base_style_ids):
        if base_style_id >= len(xfs):
            fail("presentation source style is out of range")
        base_xf = xfs[base_style_id]
        if base_xf.get("numFmtId") == NUMBER_FORMAT_ID:
            style_map[base_style_id] = base_style_id
            continue
        formatted_xf = copy.deepcopy(base_xf)
        formatted_xf.set("numFmtId", NUMBER_FORMAT_ID)
        formatted_xf.set("applyNumberFormat", "1")
        cloned_xfs.append(ElementTree.tostring(formatted_xf, encoding="utf-8"))
        style_map[base_style_id] = next_style_id
        next_style_id += 1

    if not cloned_xfs:
        return styles_xml, style_map

    container = CELL_XFS_CONTAINER_RE.search(styles_xml)
    if container is None:
        fail("presentation styles cellXfs bytes are unsupported")
    start_tag_end = styles_xml.find(b">", container.start()) + 1
    if start_tag_end <= 0 or start_tag_end > container.end():
        fail("presentation styles cellXfs start tag is invalid")
    start_tag = styles_xml[container.start() : start_tag_end]
    if not COUNT_ATTR_RE.search(start_tag):
        fail("presentation styles count attribute is missing")
    styled_start_tag = COUNT_ATTR_RE.sub(
        f' count="{next_style_id}"'.encode("ascii"),
        start_tag,
        count=1,
    )
    body_end = container.end("body")
    return (
        styles_xml[: container.start()]
        + styled_start_tag
        + styles_xml[start_tag_end:body_end]
        + b"".join(cloned_xfs)
        + styles_xml[body_end:]
    ), style_map


def worksheet_with_number_formats(
    worksheet_xml: bytes,
    styles_xml: bytes,
) -> tuple[bytes, bytes]:
    ranges = cell_ranges(worksheet_xml)
    selected: dict[str, Any] = {}
    base_style_ids: set[int] = set()
    for coordinate in number_format_coordinates():
        matches = ranges.get(coordinate, [])
        if len(matches) != 1:
            fail(f"presentation target cell is missing or duplicated: {coordinate}")
        cell_range = matches[0]
        base_style_id = cell_style_id(cell_range.xml, coordinate)
        selected[coordinate] = (cell_range, base_style_id)
        base_style_ids.add(base_style_id)

    styled_styles_xml, style_map = styles_with_number_format(
        styles_xml,
        base_style_ids,
    )
    replacements: list[tuple[int, int, bytes]] = []
    for cell_range, base_style_id in selected.values():
        replacements.append(
            (
                cell_range.start,
                cell_range.end,
                style_cell_xml(cell_range.xml, style_map[base_style_id]),
            )
        )
    ensure_non_overlapping_replacements(replacements)
    styled_worksheet = bytearray(worksheet_xml)
    for start, end, replacement in sorted(replacements, reverse=True):
        styled_worksheet[start:end] = replacement
    return bytes(styled_worksheet), styled_styles_xml


def verify_number_formats(worksheet_xml: bytes, styles_xml: bytes) -> None:
    try:
        styles_root = ElementTree.fromstring(styles_xml)
    except ElementTree.ParseError:
        fail("formatted styles XML is invalid")
    cell_xfs = styles_root.find(f"{{{SPREADSHEET_NS}}}cellXfs")
    if cell_xfs is None:
        fail("formatted styles cellXfs element is missing")
    xfs = list(cell_xfs.findall(f"{{{SPREADSHEET_NS}}}xf"))
    ranges = cell_ranges(worksheet_xml)
    for coordinate in number_format_coordinates():
        matches = ranges.get(coordinate, [])
        if len(matches) != 1:
            fail(f"formatted target cell is missing or duplicated: {coordinate}")
        style_id = cell_style_id(matches[0].xml, coordinate)
        if style_id >= len(xfs) or xfs[style_id].get("numFmtId") != NUMBER_FORMAT_ID:
            fail(f"number format was not applied to {coordinate}")


def write_presentation_package(
    parts: Mapping[str, bytes],
    worksheet_part: str,
    worksheet_xml: bytes,
    styles_xml: bytes,
    output: Path,
) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            if name == worksheet_part:
                content = worksheet_xml
            elif name == STYLES_PART:
                content = styles_xml
            archive.writestr(name, content)


def verify_presentation_package(
    before_parts: Mapping[str, bytes],
    output: Path,
    worksheet_part: str,
) -> None:
    after_parts = archive_bytes(output)
    if set(after_parts) != set(before_parts):
        fail("presentation XLSX parts differ from the candidate")
    allowed_changes = {worksheet_part, STYLES_PART}
    for name, content in before_parts.items():
        if name not in allowed_changes and after_parts[name] != content:
            fail(f"presentation changed an unexpected XLSX part: {name}")
    verify_number_formats(
        after_parts[worksheet_part],
        after_parts[STYLES_PART],
    )


def apply_number_formats(candidate: Path) -> None:
    temporary_output = candidate.with_name(
        f".{candidate.stem}.{uuid.uuid4().hex}.presentation.tmp.xlsx"
    )
    try:
        try:
            with zipfile.ZipFile(candidate) as archive:
                worksheet_part = worksheet_part_for_sheet(archive, SHEET_NAME)
        except zipfile.BadZipFile as error:
            fail(f"presentation candidate is not a valid XLSX package: {error}")
        parts = archive_bytes(candidate)
        if worksheet_part not in parts or STYLES_PART not in parts:
            fail("presentation candidate is missing required XLSX parts")
        worksheet_xml, styles_xml = worksheet_with_number_formats(
            parts[worksheet_part],
            parts[STYLES_PART],
        )
        write_presentation_package(
            parts,
            worksheet_part,
            worksheet_xml,
            styles_xml,
            temporary_output,
        )
        verify_presentation_package(parts, temporary_output, worksheet_part)
        temporary_output.replace(candidate)
    except OoxmlCellPatcherError as error:
        fail(f"presentation formatting failed: {error}")
    except OSError:
        fail("presentation formatting could not update the candidate safely")
    finally:
        if temporary_output.exists():
            temporary_output.unlink()


def publish_candidate(candidate: Path, output: Path) -> None:
    if output.exists():
        fail(f"output already exists: {output}")
    try:
        candidate.rename(output)
    except OSError:
        fail("candidate could not be published atomically")


def remove_candidate(candidate: Path) -> None:
    if not candidate.exists():
        return
    try:
        candidate.unlink()
    except OSError:
        fail("temporary candidate could not be removed")


def safe_failures(failures: Sequence[str]) -> list[str]:
    return list(failures) if failures else ["unspecified validation failure"]


def run_commercial_writer(
    commercial_csv: Path,
    template: Path,
    template_capacity: int,
    output: Path,
) -> CommercialWriterResult:
    csv_path = resolved(commercial_csv)
    template_path = resolved(template)
    output_path = resolved(output)
    result = CommercialWriterResult(csv_path, template_path, output_path)

    preflight_result = commercial_preflight.preflight(csv_path)
    result.row_count = preflight_result.row_count
    if preflight_result.status != "PASS":
        result.failures.extend(safe_failures(preflight_result.failures))
        return result
    result.checks["commercial preflight"] = "pass"

    try:
        template_path, output_path = validate_generation_paths(
            template_path,
            output_path,
            template_capacity,
        )
        result.template = template_path
        result.output = output_path
        result.checks["capacity100 profile"] = "pass"
        result.checks["output path"] = "pass"
        rows = load_commercial_rows(csv_path)
        grand_total = calculate_grand_total(rows)
        amount_text = amount_words_text(grand_total)
    except CommercialWriterError as error:
        result.failures.append(str(error))
        return result

    candidate = candidate_path_for(output_path)
    published = False
    try:
        generate_candidate(template_path, candidate, rows, amount_text)
        result.checks["candidate generation"] = "pass"

        apply_number_formats(candidate)
        result.checks["presentation formatting"] = "pass"

        reconciliation_result = commercial_reconciliation.reconcile(
            csv_path,
            candidate,
            template_capacity,
        )
        result.reconciliation_checks = dict(reconciliation_result.checks)
        if reconciliation_result.status != "PASS":
            result.failures.extend(safe_failures(reconciliation_result.failures))
            return result
        result.checks["commercial reconciliation"] = "pass"

        publish_candidate(candidate, output_path)
        published = True
        result.checks["atomic publish"] = "pass"
        result.status = "PASS"
        result.next_action = PASS_NEXT
        return result
    except CommercialWriterError as error:
        result.failures.append(str(error))
        return result
    except Exception:
        result.failures.append("unexpected internal writer failure")
        return result
    finally:
        if not published and candidate.exists():
            try:
                remove_candidate(candidate)
            except CommercialWriterError as error:
                result.failures.append(str(error))


def format_report(result: CommercialWriterResult) -> str:
    lines = [
        "COMMERCIAL_QUOTE_WRITER_REPORT_START",
        "",
        "Mode:",
        "internal draft only",
        "",
        "Input CSV:",
        str(result.commercial_csv),
        "",
        "Output XLSX:",
        str(result.output),
        "",
        "Status:",
        result.status,
        "",
        "Rows:",
        str(result.row_count),
        "",
        "Checks:",
    ]
    lines.extend(f"{name}: {status}" for name, status in result.checks.items())
    lines.extend(
        f"reconciliation {name}: {status}"
        for name, status in result.reconciliation_checks.items()
    )
    lines.extend(["", "Failures:"])
    lines.extend(result.failures if result.failures else ["none"])
    lines.extend(
        [
            "",
            "Next:",
            result.next_action,
            "",
            "Manual Igor check:",
            "required",
            "",
            "Human Approval:",
            "separate approval required",
            "",
            "COMMERCIAL_QUOTE_WRITER_REPORT_END",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_commercial_writer(
        args.commercial_csv,
        args.template,
        args.template_capacity,
        args.output,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
