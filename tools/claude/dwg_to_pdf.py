"""Convert an AutoCAD drawing to PDF with DWG TrueView (Igor 2026-11-10).

Usage: dwg_to_pdf.py <drawing.dwg> <out_folder>

Writes into <out_folder> (the drawing itself is only read, via a copy):
  drawing.pdf        - the whole model space on one A0 page (all text inside)
  drawing_tiles_N.pdf - the same page cut into overlapping pieces, six per
                       file, so that every piece is readable by eye
  drawing.txt        - the text of the drawing

Operator tool for Claude; not part of the governed chain.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject

CONSOLE = Path(
    r"C:\Program Files\Autodesk\DWG TrueView 2021 - English\accoreconsole.exe"
)
PAPER = "ISO full bleed A0 (841.00 x 1189.00 MM)"
TIMEOUT = 600
MAX_TILES = 40
PER_FILE = 6


def plot(dwg: Path, pdf: Path) -> None:
    """Plot model-space extents to one PDF page; names with spaces are fine."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        copy = work / "in.dwg"
        shutil.copyfile(dwg, copy)
        out = work / "out.pdf"
        script = work / "plot.scr"
        lines = [
            "_PLOT", "_Y", "Model", "DWG To PDF.pc3", PAPER, "_M", "_L", "_N",
            "_E", "_F", "_C", "_Y", "monochrome.ctb", "_Y", "_A", str(out),
            "_N", "_Y", "_QUIT", "_Y", "",
        ]  # fmt: skip
        script.write_text("\n".join(lines), encoding="ascii")
        with (work / "log.txt").open("wb") as log:
            subprocess.run(  # noqa: S603 - fixed local program, no shell
                [str(CONSOLE), "/i", str(copy), "/s", str(script), "/l", "en-US"],
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=TIMEOUT,
                check=False,
                cwd=work,  # TrueView drops plot.log into the current folder
            )
        if not out.is_file() or out.stat().st_size == 0:
            raise SystemExit("DWG TrueView did not produce a PDF")
        shutil.copyfile(out, pdf)


def read_text(pdf: Path) -> tuple[str, list[tuple[float, float]] | None]:
    """Text and where it sits; (note, None) when the drawing is too large."""
    points: list[tuple[float, float]] = []

    def visit(text, cm, tm, _font, _size) -> None:  # type: ignore[no-untyped-def]
        if text.strip():
            x, y = float(tm[4]), float(tm[5])
            points.append(
                (
                    x * float(cm[0]) + y * float(cm[2]) + float(cm[4]),
                    x * float(cm[1]) + y * float(cm[3]) + float(cm[5]),
                )
            )

    try:
        text = PdfReader(str(pdf)).pages[0].extract_text(visitor_text=visit) or ""
    except Exception as error:  # noqa: BLE001 - very large drawings hit pypdf limits
        note = f"(текст не извлечён: {type(error).__name__}; читать drawing.pdf)"
        return note, None
    return text, points


def tiles(pdf: Path, out: Path, points: list[tuple[float, float]] | None) -> int:
    """Cut the page into a grid over the area that holds text."""
    page = PdfReader(str(pdf)).pages[0]
    whole = points is None
    points = points or []
    box = page.mediabox
    left, bottom = float(box.left), float(box.bottom)
    right, top = float(box.right), float(box.top)
    inside = [(x, y) for x, y in points if left <= x <= right and bottom <= y <= top]
    if inside:
        pad = 40.0
        left = max(left, min(x for x, _ in inside) - pad)
        right = min(right, max(x for x, _ in inside) + pad)
        bottom = max(bottom, min(y for _, y in inside) - pad)
        top = min(top, max(y for _, y in inside) + pad)
    count = 10**6 if whole else len(inside)
    cols, rows = (2, 2) if count < 400 else (4, 3) if count < 2000 else (6, 4)
    width, height = (right - left) / cols, (top - bottom) / rows
    rects = []
    for row in range(rows - 1, -1, -1):
        for col in range(cols):
            x0 = left + col * width - width * 0.06
            x1 = left + (col + 1) * width + width * 0.06
            y0 = bottom + row * height - height * 0.06
            y1 = bottom + (row + 1) * height + height * 0.06
            if inside and not any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in inside):
                continue
            rects.append((x0, y0, x1, y1))
    rects = rects[:MAX_TILES]
    # The reader shows at most ten pages of a PDF at once: several small files.
    for part in range(0, len(rects), PER_FILE):
        writer = PdfWriter()
        for rect in rects[part : part + PER_FILE]:
            piece = writer.add_page(page)
            box = RectangleObject(rect)
            piece.mediabox = box
            piece.cropbox = box
        name = out.with_name(f"{out.stem}_{part // PER_FILE + 1}.pdf")
        with name.open("wb") as handle:
            writer.write(handle)
    return len(rects)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    dwg, folder = Path(sys.argv[1]), Path(sys.argv[2])
    if not dwg.is_file() or dwg.read_bytes()[:4] != b"AC10":
        raise SystemExit("not an AutoCAD drawing")
    if not CONSOLE.is_file():
        raise SystemExit("DWG TrueView 2021 is not installed")
    folder.mkdir(parents=True, exist_ok=True)
    pdf = folder / "drawing.pdf"
    plot(dwg, pdf)
    text, points = read_text(pdf)
    (folder / "drawing.txt").write_text(text, encoding="utf-8")
    count = tiles(pdf, folder / "drawing_tiles.pdf", points)
    print(f"written {pdf.name}, drawing.txt ({len(text)} chars), {count} tiles")


if __name__ == "__main__":
    main()
