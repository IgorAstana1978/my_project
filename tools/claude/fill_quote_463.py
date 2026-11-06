"""Fill a COPY of PTO invoice 463 with new cell values (Claude working tool).

Usage:
    python -I tools/claude/fill_quote_463.py <463.xlsx> <cells.json> <out.xlsx>

`cells.json` maps cell refs to values: text, number, or null (empty cell).
Optional key `"_positions": N` first rebuilds the table for N positions
(463 has 3): rows 16..15+N keep 463's first/middle/last row styles, the
number in B and the `=H*E` formula; rows below (ИТОГО, conditions, signatures)
move up/down and ИТОГО becomes `=SUM(I16:I<15+N>)`. Cell refs in the JSON are
in that final layout. Logo, styles, borders, column widths, row heights and
formulas otherwise stay as in 463. The source is only read; an existing output
is never overwritten.

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

FIRST, LAST = 16, 18  # table rows in 463


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


def _row(xml: str, number: int) -> re.Match[str]:
    m = re.search(rf'<row r="{number}"[^>]*>.*?</row>', xml, re.S)
    if m is None:
        raise SystemExit(f"row {number} not found in template")
    return m


def _renumber(row: str, old: int, new: int) -> str:
    row = re.sub(rf'(<row r="){old}"', rf'\g<1>{new}"', row)
    row = re.sub(rf'(<c r="[A-Z]+){old}"', rf'\g<1>{new}"', row)
    return re.sub(rf"\bH{old}\*E{old}\b", f"H{new}*E{new}", row)


def layout(xml: str, positions: int) -> str:
    """Rebuild 463's 3-row table for `positions` rows and shift what follows."""
    if positions < 1:
        raise SystemExit("_positions must be at least 1")
    rows = {n: _row(xml, n).group(0) for n in range(FIRST, LAST + 1)}
    if positions == 1:
        templates = [FIRST]
    else:
        templates = [FIRST] + [FIRST + 1] * (positions - 2) + [LAST]
    table = []
    for index, source in enumerate(templates):
        new = FIRST + index
        row = _renumber(rows[source], source, new)
        row = re.sub(
            rf'(<c r="B{new}"[^>]*>)<v>[^<]*</v>', rf"\g<1><v>{index + 1}</v>", row
        )
        table.append(row)
    start = _row(xml, FIRST).start()
    end = _row(xml, LAST).end()
    tail = xml[end:]
    delta = positions - (LAST - FIRST + 1)
    last = FIRST + positions - 1

    def shift_row(m: re.Match[str]) -> str:
        return f'{m.group(1)}{int(m.group(2)) + delta}"'

    def shift_formula(m: re.Match[str]) -> str:
        def ref(r: re.Match[str]) -> str:
            n = int(r.group(2))
            return f"{r.group(1)}{n + delta if n > LAST else n}"

        body = re.sub(r"\b([A-Z]{1,2})(\d+)\b", ref, m.group(1))
        body = body.replace(f"SUM(I{FIRST}:I{LAST})", f"SUM(I{FIRST}:I{last})")
        return f"<f>{body}</f>"

    sheet_data_end = tail.index("</sheetData>")
    body, rest = tail[:sheet_data_end], tail[sheet_data_end:]
    body = re.sub(r'(<row r=")(\d+)"', shift_row, body)
    body = re.sub(r'(<c r="[A-Z]+)(\d+)"', shift_row, body)
    body = re.sub(r"<f>([^<]*)</f>", shift_formula, body)
    xml = xml[:start] + "".join(table) + body + rest

    def dimension(m: re.Match[str]) -> str:
        return f'{m.group(1)}{int(m.group(2)) + delta}"'

    return re.sub(r'(<dimension ref="[A-Z]+\d+:[A-Z]+)(\d+)"', dimension, xml)


def fill(src: Path, cells: dict[str, object], out: Path) -> None:
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    cells = dict(cells)
    positions = cells.pop("_positions", None)
    with zipfile.ZipFile(src) as z:
        xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        if positions is not None:
            xml = layout(xml, int(str(positions)))
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
        # The calculation chain lists old cell positions; Excel rebuilds it.
        types = z.read("[Content_Types].xml").decode("utf-8")
        types = re.sub(r'<Override PartName="/xl/calcChain.xml"[^>]*/>', "", types)
        rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        rels = re.sub(r'<Relationship [^>]*Target="calcChain.xml"/>', "", rels)
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as w:
            for info in z.infolist():
                if info.filename == "xl/calcChain.xml":
                    continue
                data = z.read(info.filename)
                if info.filename == "xl/worksheets/sheet1.xml":
                    data = xml.encode("utf-8")
                elif info.filename == "xl/workbook.xml":
                    data = book.encode("utf-8")
                elif info.filename == "[Content_Types].xml":
                    data = types.encode("utf-8")
                elif info.filename == "xl/_rels/workbook.xml.rels":
                    data = rels.encode("utf-8")
                w.writestr(info, data)


if __name__ == "__main__":
    template, spec, target = (Path(a) for a in sys.argv[1:4])
    fill(template, json.loads(spec.read_text(encoding="utf-8")), target)
    print("written", target)
