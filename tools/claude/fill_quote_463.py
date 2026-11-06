"""Fill a COPY of PTO invoice 463 with new cell values (Claude working tool).

Usage:
    python -I tools/claude/fill_quote_463.py <463.xlsx> <cells.json> <out.xlsx>

`cells.json` maps cell refs to values: text, number, or null (empty cell).
Only xl/worksheets/sheet1.xml cell values and the recalc flag change; logo,
styles, borders, column widths, row heights and formulas stay as in 463.
The source is only read; an existing output is never overwritten.

This is NOT part of the governed Case chain (no Human Approval, no Case
artifact). It reproduces the manual 463-1 build of 2026-11-06.
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


def cell_xml(ref: str, style: str, value: object) -> str:
    s = f' s="{style}"' if style else ""
    if value is None:
        return f'<c r="{ref}"{s}/>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{s}><v>{value}</v></c>'
    return (
        f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">'
        f"{escape(str(value))}</t></is></c>"
    )


def fill(src: Path, cells: dict[str, object], out: Path) -> None:
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    with zipfile.ZipFile(src) as z:
        xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        for ref, value in cells.items():
            pat = re.compile(rf'<c r="{ref}"(?P<attrs>[^>]*?)(?:/>|>.*?</c>)', re.S)
            m = pat.search(xml)
            if m is None:
                raise SystemExit(f"cell {ref} not found in template")
            style = re.search(r's="(\d+)"', m.group("attrs"))
            new = cell_xml(ref, style.group(1) if style else "", value)
            xml = xml[: m.start()] + new + xml[m.end() :]
        # Drop cached formula results so Excel recalculates on open.
        xml = re.sub(r"(<f>[^<]*</f>)<v>[^<]*</v>", r"\1", xml)
        book = z.read("xl/workbook.xml").decode("utf-8")
        book = re.sub(
            r"<calcPr([^>]*)/>", r'<calcPr\1 fullCalcOnLoad="1"/>', book, count=1
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as w:
            for info in z.infolist():
                data = z.read(info.filename)
                if info.filename == "xl/worksheets/sheet1.xml":
                    data = xml.encode("utf-8")
                elif info.filename == "xl/workbook.xml":
                    data = book.encode("utf-8")
                w.writestr(info, data)


if __name__ == "__main__":
    template, spec, target = (Path(a) for a in sys.argv[1:4])
    fill(template, json.loads(spec.read_text(encoding="utf-8")), target)
    print("written", target)
