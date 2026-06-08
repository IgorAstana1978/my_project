import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from zipfile import ZIP_DEFLATED, ZipFile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "drawing_media_snapshot.py"


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


snapshot = cast(Any, load_script_module("drawing_media_snapshot_for_test", SCRIPT))

PACKAGE_PARTS = {
    "[Content_Types].xml": (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        b'<Default Extension="xml" ContentType="application/xml"/>'
        b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-'
        b'package.relationships+xml"/>'
        b'<Default Extension="png" ContentType="image/png"/>'
        b"</Types>"
    ),
    "xl/worksheets/sheet1.xml": (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        b'<sheetData/><drawing r:id="rId1"/></worksheet>'
    ),
    "xl/worksheets/_rels/sheet1.xml.rels": (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rId1" '
        b'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        b'relationships/drawing" '
        b'Target="../drawings/drawing1.xml"/>'
        b"</Relationships>"
    ),
    "xl/drawings/drawing1.xml": (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/'
        b'2006/spreadsheetDrawing" '
        b'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        b"<xdr:oneCellAnchor><xdr:pic><xdr:blipFill>"
        b'<a:blip r:embed="rId1"/>'
        b"</xdr:blipFill></xdr:pic><xdr:clientData/></xdr:oneCellAnchor>"
        b"</xdr:wsDr>"
    ),
    "xl/drawings/_rels/drawing1.xml.rels": (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rId1" '
        b'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        b'relationships/image" '
        b'Target="../media/image1.png"/>'
        b"</Relationships>"
    ),
    "xl/media/image1.png": b"fake-png-bytes",
}


def write_package(
    path: Path,
    parts: dict[str, bytes] | None = None,
    order: list[str] | None = None,
) -> None:
    package_parts = dict(PACKAGE_PARTS if parts is None else parts)
    part_order = sorted(package_parts) if order is None else order
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for part in part_order:
            archive.writestr(part, package_parts[part])


def package_without(*removed_parts: str) -> dict[str, bytes]:
    parts = dict(PACKAGE_PARTS)
    for part in removed_parts:
        del parts[part]
    return parts


def assert_snapshot_compare_fails(
    before_path: Path,
    after_path: Path,
    expected_message: str,
) -> None:
    before = snapshot.build_drawing_media_snapshot(before_path)
    after = snapshot.build_drawing_media_snapshot(after_path)

    try:
        snapshot.compare_drawing_media_snapshots(before, after)
    except snapshot.DrawingMediaSnapshotError as error:
        assert expected_message in str(error)
    else:
        raise AssertionError("snapshot comparison should fail")


def test_positive_snapshots_match(tmp_path: Path) -> None:
    before_path = tmp_path / "before.xlsx"
    after_path = tmp_path / "after.xlsx"
    write_package(before_path)
    write_package(after_path)

    before = snapshot.build_drawing_media_snapshot(before_path)
    after = snapshot.build_drawing_media_snapshot(after_path)

    snapshot.compare_drawing_media_snapshots(before, after)
    assert before == after
    assert before.media_paths == ("xl/media/image1.png",)
    assert before.drawing_paths == ("xl/drawings/drawing1.xml",)
    assert before.drawing_rels_paths == ("xl/drawings/_rels/drawing1.xml.rels",)


def test_zip_entry_order_does_not_affect_snapshot(tmp_path: Path) -> None:
    first_path = tmp_path / "first.xlsx"
    second_path = tmp_path / "second.xlsx"
    forward_order = sorted(PACKAGE_PARTS)
    reverse_order = list(reversed(forward_order))
    write_package(first_path, order=forward_order)
    write_package(second_path, order=reverse_order)

    first = snapshot.build_drawing_media_snapshot(first_path)
    second = snapshot.build_drawing_media_snapshot(second_path)

    snapshot.compare_drawing_media_snapshots(first, second)
    assert first == second


def test_missing_media_file_fails_closed(tmp_path: Path) -> None:
    before_path = tmp_path / "before.xlsx"
    after_path = tmp_path / "after.xlsx"
    write_package(before_path)
    write_package(after_path, package_without("xl/media/image1.png"))

    assert_snapshot_compare_fails(before_path, after_path, "media file missing")


def test_changed_media_file_hash_fails_closed(tmp_path: Path) -> None:
    before_path = tmp_path / "before.xlsx"
    after_path = tmp_path / "after.xlsx"
    changed_parts = dict(PACKAGE_PARTS)
    changed_parts["xl/media/image1.png"] = b"changed-image"
    write_package(before_path)
    write_package(after_path, changed_parts)

    assert_snapshot_compare_fails(before_path, after_path, "media file hash changed")


def test_changed_drawing_xml_fails_closed(tmp_path: Path) -> None:
    before_path = tmp_path / "before.xlsx"
    after_path = tmp_path / "after.xlsx"
    changed_parts = dict(PACKAGE_PARTS)
    changed_parts["xl/drawings/drawing1.xml"] = changed_parts[
        "xl/drawings/drawing1.xml"
    ].replace(
        b"oneCellAnchor",
        b"twoCellAnchor",
    )
    write_package(before_path)
    write_package(after_path, changed_parts)

    assert_snapshot_compare_fails(before_path, after_path, "drawing XML hash changed")


def test_missing_drawing_xml_fails_closed(tmp_path: Path) -> None:
    before_path = tmp_path / "before.xlsx"
    after_path = tmp_path / "after.xlsx"
    write_package(before_path)
    write_package(after_path, package_without("xl/drawings/drawing1.xml"))

    assert_snapshot_compare_fails(before_path, after_path, "drawing XML missing")


def test_changed_relationship_fails_closed(tmp_path: Path) -> None:
    before_path = tmp_path / "before.xlsx"
    after_path = tmp_path / "after.xlsx"
    changed_parts = dict(PACKAGE_PARTS)
    changed_parts["xl/drawings/_rels/drawing1.xml.rels"] = changed_parts[
        "xl/drawings/_rels/drawing1.xml.rels"
    ].replace(
        b"../media/image1.png",
        b"../media/image2.png",
    )
    write_package(before_path)
    write_package(after_path, changed_parts)

    assert_snapshot_compare_fails(before_path, after_path, "relationship changed")


def test_missing_worksheet_drawing_reference_fails_closed(tmp_path: Path) -> None:
    before_path = tmp_path / "before.xlsx"
    after_path = tmp_path / "after.xlsx"
    changed_parts = dict(PACKAGE_PARTS)
    changed_parts["xl/worksheets/sheet1.xml"] = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        b"<sheetData/></worksheet>"
    )
    write_package(before_path)
    write_package(after_path, changed_parts)

    assert_snapshot_compare_fails(
        before_path,
        after_path,
        "worksheet drawing reference missing",
    )


def test_missing_xlsx_fails_closed(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.xlsx"

    try:
        snapshot.build_drawing_media_snapshot(missing_path)
    except snapshot.DrawingMediaSnapshotError as error:
        assert "xlsx does not exist" in str(error)
    else:
        raise AssertionError("missing xlsx should fail")


def test_invalid_zip_fails_closed(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid.xlsx"
    invalid_path.write_bytes(b"not a zip")

    try:
        snapshot.build_drawing_media_snapshot(invalid_path)
    except snapshot.DrawingMediaSnapshotError as error:
        assert "invalid xlsx ZIP package" in str(error)
    else:
        raise AssertionError("invalid zip should fail")


def test_no_real_xlsx_or_manifest_files_are_added_to_git() -> None:
    status = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    changed_paths = [
        line[3:].strip() for line in status.stdout.splitlines() if line.strip()
    ]
    assert not any(path.endswith(".xlsx") for path in changed_paths)
    assert not any(
        Path(path).name.casefold() == "manifest.json" for path in changed_paths
    )
