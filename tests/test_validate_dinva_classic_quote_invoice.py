from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"main": MAIN}


def load_file(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def build_valid(tmp_path: Path) -> tuple[dict[str, Any], ModuleType, Path]:
    helpers = load_file(
        "dinva_render_test_helpers_for_validator",
        ROOT / "tests" / "test_render_dinva_classic_quote_invoice.py",
    )
    case = helpers.make_case(tmp_path)
    output = helpers.render_case(case, tmp_path / "valid.xlsx")
    validator = load_file(
        "dinva_validator_for_tests",
        ROOT / "scripts" / "validate_dinva_classic_quote_invoice.py",
    )
    return case, validator, output


def validate(case: dict[str, Any], validator: ModuleType, path: Path) -> None:
    validator.validate_or_raise(
        path,
        case["profile"],
        case["profile_sha"],
        case["document"],
        case["document_sha"],
        allow_test_profile=True,
    )


def rewrite(path: Path, mutate: Any) -> None:
    with ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    mutate(parts)
    temporary = path.with_suffix(".rewrite.xlsx")
    with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
        for name in sorted(parts):
            archive.writestr(name, parts[name])
    temporary.replace(path)


def sheet_mutation(kind: str) -> Any:
    def mutate(parts: dict[str, bytes]) -> None:
        root = ElementTree.fromstring(parts["xl/worksheets/sheet1.xml"])
        if kind in {"cell", "description"}:
            coordinate = "B10" if kind == "cell" else "F17"
            cell = root.find(f".//main:c[@r='{coordinate}']", NS)
            assert cell is not None
            text = cell.find(".//main:t", NS)
            assert text is not None
            text.text = "MUTATED"
        elif kind == "missing-row":
            sheet_data = root.find("main:sheetData", NS)
            row = root.find(".//main:row[@r='17']", NS)
            assert sheet_data is not None and row is not None
            sheet_data.remove(row)
        elif kind == "style":
            cell = root.find(".//main:c[@r='F17']", NS)
            assert cell is not None
            cell.set("s", "0")
        elif kind == "width":
            column = root.find(".//main:col[@min='3']", NS)
            assert column is not None
            column.set("width", "99")
        elif kind == "height":
            row = root.find(".//main:row[@r='17']", NS)
            assert row is not None
            row.set("ht", "99")
        elif kind == "merge":
            merge = root.find("main:mergeCells/main:mergeCell", NS)
            assert merge is not None
            merge.set("ref", "B2:C2")
        elif kind == "print":
            setup = root.find("main:pageSetup", NS)
            assert setup is not None
            setup.set("scale", "25")
        else:
            raise AssertionError(kind)
        parts["xl/worksheets/sheet1.xml"] = ElementTree.tostring(
            root, encoding="utf-8", xml_declaration=True
        )

    return mutate


def package_mutation(kind: str) -> Any:
    def mutate(parts: dict[str, bytes]) -> None:
        if kind == "logo":
            parts["xl/media/image1.png"] += b"changed"
        elif kind == "anchor":
            root = ElementTree.fromstring(parts["xl/drawings/drawing1.xml"])
            namespace = {
                "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
            }
            column = root.find("xdr:oneCellAnchor/xdr:from/xdr:col", namespace)
            assert column is not None
            column.text = "7"
            parts["xl/drawings/drawing1.xml"] = ElementTree.tostring(
                root, encoding="utf-8", xml_declaration=True
            )
        elif kind == "unexpected-part":
            parts["xl/worksheets/sheet2.xml"] = b"<unexpected/>"
        elif kind == "external":
            root = ElementTree.fromstring(parts["_rels/.rels"])
            ElementTree.SubElement(
                root,
                f"{{{REL}}}Relationship",
                {
                    "Id": "rIdExternal",
                    "Type": f"{OFFICE_REL}/hyperlink",
                    "Target": "https://example.invalid/",
                    "TargetMode": "External",
                },
            )
            parts["_rels/.rels"] = ElementTree.tostring(
                root, encoding="utf-8", xml_declaration=True
            )
        elif kind in {"calc-stale", "calc-duplicate"}:
            refs = (
                ["I17", "I20", "A1"] if kind == "calc-stale" else ["I17", "I17", "I20"]
            )
            chain = ElementTree.Element(f"{{{MAIN}}}calcChain")
            for reference in refs:
                ElementTree.SubElement(
                    chain, f"{{{MAIN}}}c", {"r": reference, "i": "1"}
                )
            parts["xl/calcChain.xml"] = ElementTree.tostring(
                chain, encoding="utf-8", xml_declaration=True
            )
            rels = ElementTree.fromstring(parts["xl/_rels/workbook.xml.rels"])
            ElementTree.SubElement(
                rels,
                f"{{{REL}}}Relationship",
                {
                    "Id": "rIdCalcChain",
                    "Type": f"{OFFICE_REL}/calcChain",
                    "Target": "calcChain.xml",
                },
            )
            parts["xl/_rels/workbook.xml.rels"] = ElementTree.tostring(
                rels, encoding="utf-8", xml_declaration=True
            )
            content_types = ElementTree.fromstring(parts["[Content_Types].xml"])
            ElementTree.SubElement(
                content_types,
                f"{{{CT}}}Override",
                {
                    "PartName": "/xl/calcChain.xml",
                    "ContentType": (
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.calcChain+xml"
                    ),
                },
            )
            parts["[Content_Types].xml"] = ElementTree.tostring(
                content_types, encoding="utf-8", xml_declaration=True
            )
        else:
            raise AssertionError(kind)

    return mutate


def test_independent_validator_accepts_clean_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DINVA_RENDERER_TEST_MODE", "1")
    case, validator, output = build_valid(tmp_path)
    validate(case, validator, output)


@pytest.mark.parametrize(
    "kind",
    [
        "cell",
        "missing-row",
        "description",
        "style",
        "width",
        "height",
        "merge",
        "print",
    ],
)
def test_validator_rejects_business_style_and_geometry_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    monkeypatch.setenv("DINVA_RENDERER_TEST_MODE", "1")
    case, validator, output = build_valid(tmp_path)
    rewrite(output, sheet_mutation(kind))
    with pytest.raises(validator.ValidationError):
        validate(case, validator, output)


@pytest.mark.parametrize(
    "kind",
    ["logo", "anchor", "unexpected-part", "external", "calc-stale", "calc-duplicate"],
)
def test_validator_rejects_package_asset_and_calcchain_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    monkeypatch.setenv("DINVA_RENDERER_TEST_MODE", "1")
    case, validator, output = build_valid(tmp_path)
    rewrite(output, package_mutation(kind))
    with pytest.raises(validator.ValidationError):
        validate(case, validator, output)


def test_validator_rejects_profile_document_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DINVA_RENDERER_TEST_MODE", "1")
    case, validator, output = build_valid(tmp_path)
    changed = dict(case)
    changed["document"] = copy.deepcopy(case["document"])
    changed["document"]["document_number"] = "OTHER"
    with pytest.raises(validator.ValidationError, match="business cell drift"):
        validate(changed, validator, output)
