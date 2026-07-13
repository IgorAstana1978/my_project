import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from openpyxl import Workbook, load_workbook  # type: ignore[import-untyped]
from pypdf import PdfReader, PdfWriter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
CORE_SCRIPT = SCRIPTS_DIR / "project_spec_extraction.py"
OPERATOR_SCRIPT = SCRIPTS_DIR / "extract_mixed_source_composition.py"
sys.path.insert(0, str(SCRIPTS_DIR))


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


extraction = cast(Any, load_module("project_spec_extraction_for_test", CORE_SCRIPT))
operator = cast(Any, load_module("mixed_source_operator_for_test", OPERATOR_SCRIPT))


def pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_text_pdf(
    path: Path,
    pages: list[list[tuple[str, int, int]]],
    *,
    image_for_empty: bool = True,
) -> Path:
    objects: dict[int, bytes] = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    page_ids = [4 + index * 2 for index in range(len(pages))]
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    image_id = 4 + len(pages) * 2
    if image_for_empty and any(not lines for lines in pages):
        image_data = b"\x80"
        objects[image_id] = (
            b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 "
            b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Length 1 >>\n"
            b"stream\n" + image_data + b"\nendstream"
        )
    for index, lines in enumerate(pages):
        page_id = page_ids[index]
        content_id = page_id + 1
        commands = [
            f"BT /F1 12 Tf {x} {y} Td ({pdf_escape(text)}) Tj ET"
            for text, x, y in lines
        ]
        content = "\n".join(commands).encode("ascii")
        if not lines and image_for_empty:
            content = b"q 100 0 0 100 72 600 cm /Im1 Do Q"
        xobject = (
            f" /XObject << /Im1 {image_id} 0 R >>"
            if not lines and image_for_empty
            else ""
        )
        objects[page_id] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >>{xobject} >> "
            f"/Contents {content_id} 0 R >>"
        ).encode()
        objects[content_id] = (
            f"<< /Length {len(content)} >>\nstream\n".encode()
            + content
            + b"\nendstream"
        )

    output = bytearray(b"%PDF-1.4\n%synthetic\n")
    offsets = [0]
    for object_number in range(1, max(objects) + 1):
        offsets.append(len(output))
        output.extend(f"{object_number} 0 obj\n".encode())
        output.extend(objects[object_number])
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    path.write_bytes(output)
    return path


def write_spec_workbook(
    path: Path,
    rows_by_sheet: dict[str, list[list[object]]],
    *,
    repeat_header: bool = False,
) -> Path:
    workbook = Workbook()
    default = workbook.active
    workbook.remove(default)
    header = [
        "Board",
        "Board name",
        "Board quantity",
        "Item",
        "Model",
        "Brand",
        "Rating",
        "Unit",
        "Quantity",
        "Note",
    ]
    for sheet_name, rows in rows_by_sheet.items():
        sheet = workbook.create_sheet(sheet_name)
        sheet.append(header)
        for index, row in enumerate(rows, start=1):
            if repeat_header and index == 2:
                sheet.append(header)
            sheet.append(row)
    workbook.save(path)
    workbook.close()
    return path


def standard_row(
    board: str = "VRU-1",
    item: str = "Breaker VA47 100A",
    quantity: object = 2,
    rating: str = "100A",
    board_quantity: object = 1,
    model: str = "VA47",
    brand: str = "EKF",
    note: str = "synthetic",
) -> list[object]:
    return [
        board,
        f"Panel {board}",
        board_quantity,
        item,
        model,
        brand,
        rating,
        "pcs",
        quantity,
        note,
    ]


def text_page(
    board: str = "VRU-1", rating: str = "100A", quantity: int = 2
) -> list[tuple[str, int, int]]:
    return [
        (f"Switchboard schedule {board} qty 1", 72, 720),
        (f"Breaker VA47 EKF {rating} {quantity} pcs", 72, 690),
        ("Project note: verify enclosure and supply boundary", 72, 660),
    ]


def first_item(draft: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], cast(list[dict[str, Any]], draft["items"])[0])


def first_component(draft: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], first_item(draft)["components"][0])


def test_pdf_with_one_switchboard(tmp_path: Path) -> None:
    pdf = write_text_pdf(tmp_path / "project.pdf", [text_page()])

    result = extraction.extract_pdf(pdf)

    assert result.pages[0]["status"] == "text_available"
    assert [board.normalized for board in result.boards] == ["VRU-1"]


def test_pdf_with_multiple_switchboards(tmp_path: Path) -> None:
    page = text_page("VRU-1") + text_page("AVR-2")
    pdf = write_text_pdf(tmp_path / "project.pdf", [page])

    result = extraction.extract_pdf(pdf)

    assert {board.normalized for board in result.boards} == {"VRU-1", "AVR-2"}


def test_pdf_switchboards_on_different_pages(tmp_path: Path) -> None:
    pdf = write_text_pdf(
        tmp_path / "project.pdf", [text_page("VRU-1"), text_page("AVR-2")]
    )

    result = extraction.extract_pdf(pdf)

    assert len(result.pages) == 2
    assert {value.page for board in result.boards for value in board.provenance} == {
        1,
        2,
    }


def test_pdf_specification_component_row(tmp_path: Path) -> None:
    pdf = write_text_pdf(tmp_path / "project.pdf", [text_page()])

    result = extraction.extract_pdf(pdf)

    assert result.boards[0].components[0].quantity == 2
    assert result.boards[0].components[0].brand == "EKF"


def test_pdf_broken_block_order_is_low_confidence(tmp_path: Path) -> None:
    page = [
        ("Switchboard schedule VRU-1 qty 1", 72, 500),
        ("Breaker VA47 EKF 100A 2 pcs", 72, 700),
        ("Project note long enough for extraction", 72, 400),
        ("Supply boundary must be checked", 72, 650),
    ]
    pdf = write_text_pdf(tmp_path / "project.pdf", [page])

    result = extraction.extract_pdf(pdf)

    assert result.pages[0]["status"] == "low_text_confidence"
    assert result.pages[0]["block_order_suspect"] is True


def test_pdf_without_text_layer_is_not_success(tmp_path: Path) -> None:
    pdf = write_text_pdf(tmp_path / "scan.pdf", [[]])

    result = extraction.extract_pdf(pdf)

    assert result.pages[0]["status"] == "image_only"
    assert result.boards == []


def test_blank_pdf_page_is_unreadable_not_image_only(tmp_path: Path) -> None:
    pdf = write_text_pdf(tmp_path / "blank.pdf", [[]], image_for_empty=False)

    result = extraction.extract_pdf(pdf)

    assert result.pages[0]["status"] == "unreadable"


def test_mixed_pdf_keeps_text_and_image_only_pages(tmp_path: Path) -> None:
    pdf = write_text_pdf(tmp_path / "mixed.pdf", [text_page(), []])

    result = extraction.extract_pdf(pdf)

    assert [page["status"] for page in result.pages] == ["text_available", "image_only"]
    assert len(result.boards) == 1


def test_corrupt_pdf_is_classified(tmp_path: Path) -> None:
    pdf = tmp_path / "corrupt.pdf"
    pdf.write_bytes(b"not a pdf")

    result = extraction.extract_pdf(pdf)

    assert result.status == "corrupt"
    assert result.pages == [{"page": 0, "status": "corrupt"}]


def test_protected_pdf_is_classified(tmp_path: Path) -> None:
    source = write_text_pdf(tmp_path / "source.pdf", [text_page()])
    reader = PdfReader(source)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.encrypt("secret")
    protected = tmp_path / "protected.pdf"
    with protected.open("wb") as output:
        writer.write(output)

    result = extraction.extract_pdf(protected)

    assert result.status == "encrypted_or_protected"
    assert result.pages == [{"page": 0, "status": "encrypted_or_protected"}]


def test_pdf_provenance_has_page_and_locator(tmp_path: Path) -> None:
    pdf = write_text_pdf(tmp_path / "project.pdf", [text_page()])

    result = extraction.extract_pdf(pdf)
    provenance = result.boards[0].provenance[0].as_dict()

    assert provenance["page"] == 1
    assert "page=1" in provenance["locator"]
    assert provenance["block_coordinates"] != ""


def test_workbook_with_one_switchboard(tmp_path: Path) -> None:
    workbook = write_spec_workbook(tmp_path / "spec.xlsx", {"Spec": [standard_row()]})

    result = extraction.extract_workbook(workbook)

    assert [board.normalized for board in result.boards] == ["VRU-1"]
    assert len(result.boards[0].components) == 1


def test_workbook_with_multiple_switchboards_on_sheet(tmp_path: Path) -> None:
    workbook = write_spec_workbook(
        tmp_path / "spec.xlsx",
        {"Spec": [standard_row("VRU-1"), standard_row("AVR-2")]},
    )

    result = extraction.extract_workbook(workbook)

    assert {board.normalized for board in result.boards} == {"VRU-1", "AVR-2"}


def test_workbook_switchboards_on_different_sheets(tmp_path: Path) -> None:
    workbook = write_spec_workbook(
        tmp_path / "spec.xlsx",
        {"Input": [standard_row("VRU-1")], "Output": [standard_row("AVR-2")]},
    )

    result = extraction.extract_workbook(workbook)

    assert len(result.sheets) == 2
    assert {board.normalized for board in result.boards} == {"VRU-1", "AVR-2"}


def test_workbook_merged_board_cells(tmp_path: Path) -> None:
    workbook_path = write_spec_workbook(
        tmp_path / "spec.xlsx",
        {"Spec": [standard_row(), standard_row(item="Contactor KM1", quantity=1)]},
    )
    workbook = load_workbook(workbook_path)
    sheet = workbook["Spec"]
    sheet.merge_cells("A2:A3")
    workbook.save(workbook_path)
    workbook.close()

    result = extraction.extract_workbook(workbook_path)

    assert len(result.boards) == 1
    assert len(result.boards[0].components) == 2


def test_workbook_repeated_headers_are_skipped(tmp_path: Path) -> None:
    workbook = write_spec_workbook(
        tmp_path / "spec.xlsx",
        {"Spec": [standard_row(), standard_row(item="Contactor KM1", quantity=1)]},
        repeat_header=True,
    )

    result = extraction.extract_workbook(workbook)

    assert len(result.boards[0].components) == 2


def test_workbook_missing_quantity_requires_review(tmp_path: Path) -> None:
    workbook = write_spec_workbook(
        tmp_path / "spec.xlsx", {"Spec": [standard_row(quantity=None)]}
    )

    result = extraction.extract_workbook(workbook)

    assert result.boards[0].components[0].quantity is None
    assert (
        "missing or doubtful component quantity"
        in result.boards[0].components[0].red_flags
    )


def test_workbook_possible_duplicate_requires_review(tmp_path: Path) -> None:
    workbook = write_spec_workbook(
        tmp_path / "spec.xlsx", {"Spec": [standard_row(), standard_row()]}
    )

    result = extraction.extract_workbook(workbook)

    assert "possible duplicate workbook row" in result.boards[0].components[1].red_flags


def test_workbook_provenance_has_sheet_row_and_cells(tmp_path: Path) -> None:
    workbook = write_spec_workbook(tmp_path / "spec.xlsx", {"Spec": [standard_row()]})

    result = extraction.extract_workbook(workbook)
    provenance = result.boards[0].components[0].provenance[0].as_dict()

    assert provenance["sheet"] == "Spec"
    assert provenance["row"] == 2
    assert provenance["cell_range"] == "A2:J2"


def mixed_artifacts(
    tmp_path: Path,
    *,
    pdf_board: str = "VRU-1",
    workbook_board: str = "VRU-1",
    pdf_rating: str = "100A",
    workbook_rating: str = "100A",
    pdf_quantity: int = 2,
    workbook_quantity: object = 2,
) -> Any:
    pdf = write_text_pdf(
        tmp_path / "project.pdf",
        [text_page(pdf_board, pdf_rating, pdf_quantity)],
    )
    workbook = write_spec_workbook(
        tmp_path / "spec.xlsx",
        {
            "Spec": [
                standard_row(
                    workbook_board,
                    quantity=workbook_quantity,
                    rating=workbook_rating,
                )
            ]
        },
    )
    return extraction.build_artifacts(pdf, workbook)


def sparse_pdf_mixed_artifacts(
    tmp_path: Path,
    workbook_row: list[object],
) -> Any:
    pdf = write_text_pdf(
        tmp_path / "project.pdf",
        [
            [
                ("Switchboard schedule VRU-1 qty 1", 72, 720),
                ("Breaker VA47 2 pcs", 72, 690),
                ("Project note: verify supply boundary", 72, 660),
            ]
        ],
    )
    workbook = write_spec_workbook(tmp_path / "spec.xlsx", {"Spec": [workbook_row]})
    return extraction.build_artifacts(pdf, workbook)


def test_same_switchboard_is_matched_between_sources(tmp_path: Path) -> None:
    artifacts = mixed_artifacts(tmp_path)

    assert artifacts.summary["switchboards_matched"] == 1
    assert len(artifacts.draft["items"]) == 1


def test_pdf_designation_and_workbook_composition_are_combined(tmp_path: Path) -> None:
    artifacts = mixed_artifacts(tmp_path)
    item = first_item(artifacts.draft)

    assert item["normalized_designation"] == "VRU-1"
    assert {value["source_type"] for value in item["provenance"]} == {"pdf", "workbook"}
    assert item["components"]


def test_matching_component_quantity_merges_without_quantity_conflict(
    tmp_path: Path,
) -> None:
    artifacts = mixed_artifacts(tmp_path)
    component = first_component(artifacts.draft)

    assert component["quantity_guess"] == 2
    assert not any("quantity" in value["type"] for value in component["conflicts"])


def test_workbook_brand_enriches_sparse_pdf_component(tmp_path: Path) -> None:
    artifacts = sparse_pdf_mixed_artifacts(
        tmp_path,
        standard_row(
            item="Breaker VA47",
            rating="",
            brand="EKF",
            note="",
        ),
    )
    component = first_component(artifacts.draft)

    assert component["brand_guess"] == "EKF"
    assert not any(
        value["type"] == "component_brand_mismatch" for value in component["conflicts"]
    )


def test_workbook_rating_enriches_sparse_pdf_component(tmp_path: Path) -> None:
    artifacts = sparse_pdf_mixed_artifacts(
        tmp_path,
        standard_row(
            item="Breaker VA47",
            rating="100A",
            brand="",
            note="",
        ),
    )
    component = first_component(artifacts.draft)

    assert component["rating_guess"] == "100A"
    assert not any(
        value["type"] == "component_rating_mismatch" for value in component["conflicts"]
    )


def test_workbook_note_enriches_sparse_pdf_component(tmp_path: Path) -> None:
    artifacts = sparse_pdf_mixed_artifacts(
        tmp_path,
        standard_row(
            item="Breaker VA47",
            rating="",
            brand="",
            note="Mount on DIN rail",
        ),
    )
    component = first_component(artifacts.draft)

    assert component["note_guess"] == "Mount on DIN rail"
    assert {value["source_type"] for value in component["provenance"]} == {
        "pdf",
        "workbook",
    }


def test_different_notes_create_conflict_without_automatic_choice(
    tmp_path: Path,
) -> None:
    workbook = write_spec_workbook(
        tmp_path / "spec.xlsx",
        {
            "Spec": [
                standard_row(note="Install left"),
                standard_row(note="Install right"),
            ]
        },
    )

    artifacts = extraction.build_artifacts(None, workbook)
    component = first_component(artifacts.draft)

    assert component["note_guess"] is None
    assert any(
        value["type"] == "component_note_mismatch" for value in component["conflicts"]
    )


def test_component_quantity_conflict_is_not_silently_resolved(tmp_path: Path) -> None:
    artifacts = mixed_artifacts(tmp_path, pdf_quantity=2, workbook_quantity=3)
    component = first_component(artifacts.draft)

    assert component["quantity_guess"] is None
    assert any(
        value["type"] == "component_quantity_mismatch"
        for value in component["conflicts"]
    )


def test_component_rating_conflict_is_not_silently_resolved(tmp_path: Path) -> None:
    artifacts = mixed_artifacts(tmp_path, pdf_rating="100A", workbook_rating="125A")
    component = first_component(artifacts.draft)

    assert component["rating_guess"] is None
    assert any(
        value["type"] == "component_rating_mismatch" for value in component["conflicts"]
    )


def test_switchboard_only_in_pdf_is_unmatched(tmp_path: Path) -> None:
    artifacts = mixed_artifacts(tmp_path, workbook_board="AVR-2")

    assert artifacts.summary["switchboards_unmatched"] == 2
    assert any(
        value["type"] == "switchboard_present_in_one_source"
        for item in artifacts.draft["items"]
        for value in item["conflicts"]
    )


def test_switchboard_only_in_workbook_is_unmatched(tmp_path: Path) -> None:
    artifacts = mixed_artifacts(tmp_path, pdf_board="AVR-2")

    assert artifacts.summary["switchboards_unmatched"] == 2
    assert {item["normalized_designation"] for item in artifacts.draft["items"]} == {
        "AVR-2",
        "VRU-1",
    }


def test_ambiguous_designations_are_not_merged(tmp_path: Path) -> None:
    artifacts = mixed_artifacts(tmp_path, pdf_board="VRU-1A", workbook_board="VRU-1")

    assert artifacts.summary["switchboards_matched"] == 0
    assert any(
        value["type"] == "ambiguous_switchboard_match"
        for item in artifacts.draft["items"]
        for value in item["conflicts"]
    )


def test_similar_significant_numbers_are_not_merged(tmp_path: Path) -> None:
    artifacts = mixed_artifacts(tmp_path, pdf_board="VRU-1", workbook_board="VRU-11")

    assert artifacts.summary["switchboards_matched"] == 0
    assert len(artifacts.draft["items"]) == 2


def test_provenance_survives_merge(tmp_path: Path) -> None:
    artifacts = mixed_artifacts(tmp_path)
    component = first_component(artifacts.draft)

    assert {value["source_type"] for value in component["provenance"]} == {
        "pdf",
        "workbook",
    }
    assert all(value["locator"] for value in component["provenance"])


def test_conflict_appears_in_existing_review_card(tmp_path: Path) -> None:
    pdf = write_text_pdf(tmp_path / "project.pdf", [text_page(quantity=2)])
    workbook = write_spec_workbook(
        tmp_path / "spec.xlsx", {"Spec": [standard_row(quantity=3)]}
    )
    output_dir = tmp_path / "output"

    result = operator.run_operator(pdf, workbook, output_dir)
    markdown = (output_dir / operator.REVIEW_NAME).read_text(encoding="utf-8")

    assert result.status == "PASS", result.red_flags
    assert "## Требует проверки Игоря" in markdown
    assert "different component quantities between sources" in markdown


def test_workbook_note_is_visible_in_existing_review_card(tmp_path: Path) -> None:
    pdf = write_text_pdf(
        tmp_path / "project.pdf",
        [
            [
                ("Switchboard schedule VRU-1 qty 1", 72, 720),
                ("Breaker VA47 2 pcs", 72, 690),
                ("Project note: verify supply boundary", 72, 660),
            ]
        ],
    )
    workbook = write_spec_workbook(
        tmp_path / "spec.xlsx",
        {
            "Spec": [
                standard_row(
                    item="Breaker VA47",
                    rating="",
                    brand="",
                    note="Mount on DIN rail",
                )
            ]
        },
    )
    output_dir = tmp_path / "output"

    result = operator.run_operator(pdf, workbook, output_dir)
    markdown = (output_dir / operator.REVIEW_NAME).read_text(encoding="utf-8")

    assert result.status == "PASS", result.red_flags
    assert "note_guess" in markdown
    assert "Mount on DIN rail" in markdown


def test_human_approval_is_never_set_automatically(tmp_path: Path) -> None:
    artifacts = mixed_artifacts(tmp_path)
    safety = artifacts.draft["safety"]

    assert all(value is False for key, value in safety.items() if key != "status")
    serialized = json.dumps(artifacts.draft)
    for forbidden in (
        '"composition_approved": true',
        '"price_confirmed_by_igor": true',
        '"commercial_csv_approved": true',
        '"quote_approved": true',
        '"client_send_approved": true',
        '"procurement_approved": true',
        '"production_approved": true',
    ):
        assert forbidden not in serialized


def test_generated_draft_passes_existing_preliminary_validator(tmp_path: Path) -> None:
    pdf = write_text_pdf(tmp_path / "project.pdf", [text_page()])
    output_dir = tmp_path / "output"

    result = operator.run_operator(pdf, None, output_dir)

    assert result.status == "PASS", result.red_flags
    assert result.checks["preliminary draft validation"] == "pass"
    assert result.checks["source bundle verification and review card"] == "pass"


def test_cli_requires_at_least_one_source(tmp_path: Path) -> None:
    result = operator.run_operator(None, None, tmp_path / "output")

    assert result.status == "FAIL"
    assert "at least one source" in result.red_flags[0]
    assert not result.output_dir.exists()


def test_cli_rejects_output_inside_git(tmp_path: Path) -> None:
    pdf = write_text_pdf(tmp_path / "project.pdf", [text_page()])
    output = PROJECT_ROOT / "unsafe-generated-output"

    result = operator.run_operator(pdf, None, output)

    assert result.status == "FAIL"
    assert not output.exists()


def test_pdf_only_operator_smoke(tmp_path: Path) -> None:
    pdf = write_text_pdf(tmp_path / "project.pdf", [text_page()])
    output = tmp_path / "pdf-output"

    result = operator.run_operator(pdf, None, output)

    assert result.status == "PASS", result.red_flags
    assert (output / operator.REVIEW_NAME).is_file()


def test_workbook_only_operator_smoke(tmp_path: Path) -> None:
    workbook = write_spec_workbook(tmp_path / "spec.xlsx", {"Spec": [standard_row()]})
    output = tmp_path / "workbook-output"

    result = operator.run_operator(None, workbook, output)

    assert result.status == "PASS", result.red_flags
    assert (output / operator.REVIEW_NAME).is_file()


def test_mixed_source_operator_smoke(tmp_path: Path) -> None:
    pdf = write_text_pdf(tmp_path / "project.pdf", [text_page()])
    workbook = write_spec_workbook(tmp_path / "spec.xlsx", {"Spec": [standard_row()]})
    output = tmp_path / "mixed-output"

    result = operator.run_operator(pdf, workbook, output)

    assert result.status == "PASS"
    assert result.summary["switchboards_matched"] == 1
    assert (output / operator.MANIFEST_NAME).is_file()
    assert (output / operator.DRAFT_NAME).is_file()
    assert (output / operator.REVIEW_NAME).is_file()


def pdf_block(text: str, x: float, y: float, number: int) -> Any:
    return extraction.PdfBlock(text, x, y, number)


def test_schematic_qf_line_with_qf0_and_qf1_is_split() -> None:
    segments = extraction.split_qf_segments_from_text(
        "QF0ВН-323P 25ААВР QF1АВДТ32 2PC16/30мА розеточная сеть"
    )

    assert len(segments) == 2
    assert segments[0].startswith("QF0")
    assert segments[1].startswith("QF1")


def test_schematic_title_without_space_finds_board_designations() -> None:
    assert extraction.schematic_board_designations(
        "Формат А4 Принципиальная схема группового щитаЩО6"
    ) == ["ЩО6"]
    assert extraction.schematic_board_designations(
        "Формат А3 Принципиальная схема группового щитаНЩР17"
    ) == ["НЩР17"]
    assert extraction.schematic_board_designations(
        "Формат А3 Принципиальная схема группового щитаАВР17"
    ) == ["АВР17"]


def test_source_reference_to_vru_is_classified_as_reference() -> None:
    assert extraction.is_source_reference("от ВРУ 3А")
    assert extraction.is_source_reference("питание от ВРУ 3А")
    assert extraction.is_source_reference("существующая группа от ВРУ")
    assert not extraction.is_source_reference(
        "Принципиальная схема группового щитаВРУ1"
    )


def test_real_schematic_title_vru_is_not_globally_blocked() -> None:
    blocks = [
        pdf_block("Принципиальная схема группового щита", 10, 10, 1),
        pdf_block("ВРУ", 20, 20, 2),
        pdf_block("1", 30, 20, 3),
    ]

    titles = extraction.find_schematic_board_titles(
        blocks, "Принципиальная схема группового щитаВРУ1"
    )

    assert [title.normalized for title in titles] == ["ВРУ-1"]


def test_qf_apparatus_tokens_are_parsed_deterministically() -> None:
    cases = {
        "QF0 ВА88-32 3P 63А": ("ВА88-32", "3P", "63А"),
        "QF0 ВН-32 3P 25А": ("ВН-32", "3P", "25А"),
        "QF1 АВДТ32 2P C16/30мА": ("АВДТ32", "2P", "C16/30мА"),
        "QF2 АВДТ32 2P C20/30мА": ("АВДТ32", "2P", "C20/30мА"),
    }

    for raw, expected in cases.items():
        parsed = extraction.parse_qf_apparatus(raw)

        assert (parsed["model"], parsed["poles"], parsed["rating"]) == expected


def test_plan_without_schematic_evidence_does_not_create_schematic_title() -> None:
    blocks = [
        pdf_block("План розеточных сетей 2-го этажа", 10, 10, 1),
        pdf_block("ЩО.6", 20, 20, 2),
        pdf_block("АВР", 30, 20, 3),
        pdf_block("НЩР", 40, 20, 4),
    ]

    assert extraction.find_schematic_board_titles(blocks, "") == []


def test_multiple_schematic_zones_can_leave_qf_assignment_ambiguous() -> None:
    titles = [
        extraction.SchematicBoardTitle(
            "ЩО6",
            "ЩО-6",
            "Принципиальная схема группового щита ЩО6",
            pdf_block("", 0, 0, 1),
        ),
        extraction.SchematicBoardTitle(
            "НЩР17",
            "НЩР-17",
            "Принципиальная схема группового щита НЩР17",
            pdf_block("", 20, 0, 2),
        ),
    ]
    segment = extraction.QfSegment(
        "QF1",
        "QF1 АВДТ32 2P C16/30мА",
        pdf_block("", 10, 0, 3),
    )

    assert extraction.nearest_schematic_board(segment, titles) is None


def test_qf_segments_from_blocks_reports_detected_segments() -> None:
    segments = extraction.qf_segments_from_blocks(
        [
            pdf_block("QF0", 72, 690, 1),
            pdf_block("ВА88-32", 72, 680, 2),
            pdf_block("3P 63А", 72, 670, 3),
            pdf_block("QF1", 172, 690, 4),
            pdf_block("АВДТ32 2P", 172, 680, 5),
            pdf_block("C16/30мА", 172, 670, 6),
        ],
        "",
    )

    assert [segment.designation for segment in segments] == ["QF0", "QF1"]


def test_schematic_qf_component_key_keeps_same_model_qfs_distinct() -> None:
    first = extraction.qf_component_from_segment(
        extraction.QfSegment(
            "QF1",
            "QF1 АВДТ32 2P C16/30мА",
            pdf_block("QF1", 1, 1, 1),
        ),
        "project.pdf",
        1,
        0.82,
    )
    second = extraction.qf_component_from_segment(
        extraction.QfSegment(
            "QF2",
            "QF2 АВДТ32 2P C16/30мА",
            pdf_block("QF2", 2, 1, 2),
        ),
        "project.pdf",
        1,
        0.82,
    )

    assert extraction.component_key(first) == "qf:QF1"
    assert extraction.component_key(second) == "qf:QF2"


def test_schematic_qf_provenance_keeps_page_raw_segment_and_locator() -> None:
    component = extraction.qf_component_from_segment(
        extraction.QfSegment(
            "QF1",
            "QF1 АВДТ32 2P C20/30мА",
            pdf_block("QF1", 72, 690, 3),
        ),
        "project.pdf",
        1,
        0.82,
    )

    provenance = component.provenance[0].as_dict()

    assert provenance["page"] == 1
    assert "QF1" in provenance["raw_text"]
    assert "qf=QF1" in provenance["locator"]
