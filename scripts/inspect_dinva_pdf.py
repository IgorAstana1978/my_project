"""Independent PDF text/font/logo/glyph-bound checks using bundled runtime.

Run with the configured bundled Python (Pillow + pypdfium2 + pypdf).
This inspector never authors a document and imports no producer/renderer code.
"""

import argparse
import base64
import collections
import hashlib
import io
import json
import sys
import unicodedata
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfReader


def normalize(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).split()).replace("\u00ad", "")


def clip_geometry(page: Any) -> list[dict[str, Any]]:
    """Native Excel rectangular clipping paths, independently tracked per text op."""
    box = page.cropbox
    clip = tuple(float(x) for x in box)
    matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    stack = []
    path = None
    owner = None
    path_owner = None
    baseline = None
    windows = []
    for op_index, (args, op) in enumerate(page.get_contents().operations):
        if op == b"q":
            stack.append((matrix, clip, owner))
        elif op == b"Q":
            matrix, clip, owner = stack.pop()
        elif op == b"cm":
            a, b, c, d, e, f = matrix
            g, h, i, j, k, offset_y = (float(x) for x in args)
            matrix = (
                a * g + c * h,
                b * g + d * h,
                a * i + c * j,
                b * i + d * j,
                a * k + c * offset_y + e,
                b * k + d * offset_y + f,
            )
        elif op == b"re":
            path_owner = op_index if matrix == (1.0, 0.0, 0.0, 1.0, 0.0, 0.0) else None
            x, y, w, h = (float(v) for v in args)
            a, b, c, d, e, f = matrix
            points = [
                (a * u + c * v + e, b * u + d * v + f)
                for u, v in [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
            ]
            path = (
                min(u for u, v in points),
                min(v for u, v in points),
                max(u for u, v in points),
                max(v for u, v in points),
            )
        elif op in (b"W", b"W*"):
            if path is None:
                raise ValueError("unsupported nonrectangular text clipping path")
            clip = (
                max(clip[0], path[0]),
                max(clip[1], path[1]),
                min(clip[2], path[2]),
                min(clip[3], path[3]),
            )
            owner = path_owner
        elif op == b"n":
            path = None
        elif op == b"Tm":
            a, b, c, d, e, f = matrix
            baseline = (
                a * float(args[4]) + c * float(args[5]) + e,
                b * float(args[4]) + d * float(args[5]) + f,
            )
        elif op in (b"Tj", b"TJ"):
            windows.append({"clip": clip, "rectangle_op": owner, "baseline": baseline})
    return windows


def clipping_windows(page: Any) -> list[tuple[float, float, float, float]]:
    return [record["clip"] for record in clip_geometry(page)]


def measure_vertical_edges(pdf: Path) -> dict:
    """Only ink edges with a fitting baseline; no font/layout changes.

    Full-line, horizontal, unknown or colliding overflow stays HOLD. Outward
    0.0001pt rounding prevents inward PDF-number serialization, not size tuning.
    """
    reader = PdfReader(pdf)
    actual = pdfium.PdfDocument(str(pdf))
    corrections = []
    for page_index, page in enumerate(actual):
        objects = list(page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_TEXT]))
        records = clip_geometry(reader.pages[page_index])
        if len(objects) != len(records):
            raise ValueError("native text/clip association unavailable")
        bounds = [o.get_bounds() for o in objects]
        adjusted = {}
        for i, (box, record) in enumerate(zip(bounds, records, strict=True)):
            left, bottom, right, top = box
            x0, y0, x1, y1 = record["clip"]
            if left >= x0 and bottom >= y0 and right <= x1 and top <= y1:
                continue
            baseline = record["baseline"]
            owner = record["rectangle_op"]
            if (
                owner is None
                or baseline is None
                or left < x0
                or right > x1
                or not y0 <= baseline[1] <= y1
            ):
                raise ValueError(
                    "native overflow is not a recoverable vertical glyph edge"
                )
            if any(
                j != i and left < b[2] and right > b[0] and bottom < b[3] and top > b[1]
                for j, b in enumerate(bounds)
            ):
                raise ValueError("native glyph recovery would overlap other text")
            w, h = page.get_size()
            if bottom < 0 or top > h or left < 0 or right > w:
                raise ValueError("native glyph outside page")
            old, _ = reader.pages[page_index].get_contents().operations[owner]
            previous = adjusted.get(
                owner, (float(old[1]), float(old[1]) + float(old[3]))
            )
            adjusted[owner] = (min(previous[0], bottom), max(previous[1], top))
        for owner, (bottom, top) in adjusted.items():
            old, _ = reader.pages[page_index].get_contents().operations[owner]
            lower = Decimal(str(bottom)).quantize(
                Decimal(".0001"), rounding=ROUND_FLOOR
            )
            upper = Decimal(str(top)).quantize(Decimal(".0001"), rounding=ROUND_CEILING)
            corrections.append(
                {
                    "page": page_index,
                    "rectangle_op": owner,
                    "old": [float(x) for x in old],
                    "new": [
                        float(old[0]),
                        float(lower),
                        float(old[2]),
                        float(upper - lower),
                    ],
                    "reason": "MEASURED_VERTICAL_GLYPH_EDGE",
                }
            )
        page.close()
    actual.close()
    return {
        "status": "MEASURED",
        "native_pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "corrections": corrections,
    }


def inspect(pdf: Path, expected: dict) -> dict:
    reader = PdfReader(pdf)
    if reader.is_encrypted or len(reader.pages) != expected["page_count"]:
        raise ValueError("PDF missing/encrypted/extra pages")
    metadata = reader.metadata or {}
    for key, value in expected["bindings"].items():
        if metadata.get(key) != value:
            raise ValueError("PDF source metadata binding drift")
    actual = pdfium.PdfDocument(str(pdf))
    texts = []
    for index, page in enumerate(actual):
        textpage = page.get_textpage()
        # pypdf decodes ToUnicode hyphens correctly where PDFium returns U+FFFE.
        # PDFium remains the independent glyph geometry/render engine.
        texts.append(reader.pages[index].extract_text())
        width, height = page.get_size()
        for i in range(textpage.count_chars()):
            char = textpage.get_text_range(i, 1)
            if not char.strip():
                continue
            left, bottom, right, top = textpage.get_charbox(i)
            if min(left, bottom) < 0 or right > width or top > height:
                raise ValueError("PDF glyph clipping outside page")
        objects = list(page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_TEXT]))
        windows = clipping_windows(reader.pages[index])
        if len(objects) != len(windows):
            raise ValueError("PDF text/clip association unavailable")
        for object_index, (obj, clip) in enumerate(zip(objects, windows, strict=True)):
            left, bottom, right, top = obj.get_bounds()
            if left < clip[0] or bottom < clip[1] or right > clip[2] or top > clip[3]:
                raise ValueError(
                    f"PDF cell/text clipping: object {object_index}, "
                    f"{(left,bottom,right,top)} outside {clip}"
                )
        textpage.close()
        page.close()
    actual.close()
    text = normalize("\n".join(texts))
    for fragment, count in collections.Counter(
        normalize(x) for x in expected["texts"]
    ).items():
        if fragment and text.count(fragment) < count:
            raise ValueError("PDF missing business text: " + fragment[:120])
    fonts = []
    for page in reader.pages:
        for font in page["/Resources"].get("/Font", {}).values():
            obj = font.get_object()
            name = str(obj.get("/BaseFont", ""))
            if name.lstrip("/").split("+")[-1] not in {
                "TimesNewRomanPSMT",
                "TimesNewRomanPS-BoldMT",
                "TimesNewRomanPS-BoldItalicMT",
            }:
                raise ValueError("PDF canonical font drift: " + name)
            descendants = obj.get("/DescendantFonts", [obj])
            for child in descendants:
                desc = child.get_object().get("/FontDescriptor")
                if desc is None or not any(
                    k in desc.get_object()
                    for k in ("/FontFile", "/FontFile2", "/FontFile3")
                ):
                    raise ValueError("PDF font not embedded")
            fonts.append(name)
    if not fonts:
        raise ValueError("PDF fonts missing")
    logo = Image.open(io.BytesIO(base64.b64decode(expected["logo_base64"]))).convert(
        "RGB"
    )
    matches = 0
    for page in reader.pages:
        for image in page.images:
            pixels = image.image.convert("RGB")
            if pixels.size == logo.size and pixels.tobytes() == logo.tobytes():
                matches += 1
    if matches < 1:
        raise ValueError("PDF canonical logo missing/changed")
    return {
        "status": "PASS",
        "page_count": len(reader.pages),
        "fonts": sorted(set(fonts)),
        "logo_matches": matches,
        "client_send_authorized": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pdf", type=Path, required=True)
    p.add_argument("--pdf-sha256", required=True)
    p.add_argument("--expectations", type=Path)
    p.add_argument("--expectations-sha256")
    p.add_argument("--measure-clips", action="store_true")
    a = p.parse_args()
    try:
        pdf_raw = a.pdf.read_bytes()
        if hashlib.sha256(pdf_raw).hexdigest() != a.pdf_sha256:
            raise ValueError("PDF subject SHA mismatch")
        script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        runtime_sha = hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
        exp_raw = a.expectations.read_bytes() if a.expectations else None
        if a.measure_clips:
            if a.expectations is not None or a.expectations_sha256 is not None:
                raise ValueError("measurement cannot claim validation")
            result = measure_vertical_edges(a.pdf)
        else:
            if a.expectations is None or a.expectations_sha256 is None:
                raise ValueError("validation expectations required")
            if hashlib.sha256(exp_raw).hexdigest() != a.expectations_sha256:
                raise ValueError("expectations SHA mismatch")
            result = inspect(a.pdf, json.loads(exp_raw))
        if a.pdf.read_bytes() != pdf_raw or (
            a.expectations and a.expectations.read_bytes() != exp_raw
        ):
            raise ValueError("PDF/expectations changed during inspection")
        if (
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != script_sha
            or hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
            != runtime_sha
        ):
            raise ValueError("inspector/runtime changed during inspection")
        print(
            json.dumps(
                {
                    **result,
                    "pdf_sha256": a.pdf_sha256,
                    "expectations_sha256": a.expectations_sha256,
                    "runtime_sha256": runtime_sha,
                    "inspector_sha256": script_sha,
                }
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
