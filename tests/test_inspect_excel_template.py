import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inspect_excel_template.py"


def write_minimal_xlsx(path: Path) -> None:
    with ZipFile(path, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Invoice" sheetId="1" r:id="rId1"/>
    <sheet name="Terms" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>
""",
        )
        workbook.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Target="sharedStrings.xml"/>
</Relationships>
""",
        )
        workbook.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>Invoice template</t></si>
</sst>
""",
        )
        workbook.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:C3"/>
  <sheetData>
    <row r="1"><c r="A1" t="s"><v>0</v></c></row>
    <row r="2">
      <c r="B2"><v>5</v></c>
      <c r="C2"><f>B2*2</f><v>10</v></c>
    </row>
  </sheetData>
  <mergeCells count="1"><mergeCell ref="A1:C1"/></mergeCells>
</worksheet>
""",
        )
        workbook.writestr(
            "xl/worksheets/sheet2.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:B1"/>
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>Terms</t></is></c>
      <c r="B1" t="b"><v>1</v></c>
    </row>
  </sheetData>
</worksheet>
""",
        )


def run_inspector(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_inspects_xlsx_without_modifying_it(tmp_path: Path) -> None:
    workbook = tmp_path / "invoice.xlsx"
    write_minimal_xlsx(workbook)
    before = workbook.read_bytes()

    result = run_inspector(workbook)

    assert result.returncode == 0
    assert result.stderr == ""
    assert workbook.read_bytes() == before
    assert "Sheets:\n- Invoice\n- Terms" in result.stdout
    assert "Size: 3 rows x 3 columns" in result.stdout
    assert "A1:C1" in result.stdout
    assert "C2 = =B2*2" in result.stdout
    assert "A1 = Invoice template" in result.stdout
    assert "A1 = Terms" in result.stdout
    assert "B1 = TRUE" in result.stdout


def test_warns_for_legacy_xls_without_reading_it(tmp_path: Path) -> None:
    workbook = tmp_path / "legacy.xls"
    workbook.write_bytes(b"legacy workbook placeholder")

    result = run_inspector(workbook)

    assert result.returncode == 0
    assert result.stderr == ""
    assert ".xls is an old Excel format" in result.stdout
    assert "Convert it to .xlsx" in result.stdout
    assert "Sheets:" not in result.stdout
