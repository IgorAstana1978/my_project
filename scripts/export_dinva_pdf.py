"""Read-only PDF preflight and isolated TEST-ONLY native PDF conformance.

Real/production PDF approval and export are NOT_IMPLEMENTED_PENDING_WU5.
No artifact, runtime contract or mutable rollout log can enable production.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import render_dinva_classic_quote_invoice as renderer
import validate_dinva_classic_quote_invoice as validator
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, FloatObject, NameObject, NumberObject

NATIVE_ENGINE = Path(__file__).with_name("export_dinva_pdf_native.ps1")
NATIVE_GUARD = "throw 'DIRECT_NATIVE_PDF_EXPORT_CLOSED_USE_GOVERNED_EXPORTER'\n"
INSPECTOR = Path(__file__).with_name("inspect_dinva_pdf.py")
PRODUCTION_STATUS = "NOT_IMPLEMENTED_PENDING_WU5"
TEST_AUTHORIZATION = "TEST_ONLY_DINVA_PDF_EXPORT"
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
SYSTEM_FONT_FILES = {
    "TimesNewRomanPSMT": "times.ttf",
    "TimesNewRomanPS-BoldMT": "timesbd.ttf",
    "TimesNewRomanPS-BoldItalicMT": "timesbi.ttf",
}


def checked_font(raw: bytes, expected_name: str) -> None:
    """Read-only sfnt name/embedding-right checks; no font substitution/subsetting."""
    require(raw[:4] == b"\x00\x01\x00\x00", "TrueType sfnt required")
    count = struct.unpack_from(">H", raw, 4)[0]
    tables = {}
    for i in range(count):
        tag, _, offset, size = struct.unpack_from(">4sIII", raw, 12 + 16 * i)
        require(offset + size <= len(raw), "font table bounds invalid")
        tables[tag] = (offset, size)
    names_offset, names_size = tables[b"name"]
    _, n, strings = struct.unpack_from(">HHH", raw, names_offset)
    names = []
    for i in range(n):
        platform, _, _, name_id, size, offset = struct.unpack_from(
            ">HHHHHH", raw, names_offset + 6 + 12 * i
        )
        if name_id == 6:
            require(strings + offset + size <= names_size, "font name bounds invalid")
            value = raw[
                names_offset + strings + offset : names_offset + strings + offset + size
            ]
            names.append(
                value.decode("utf-16-be" if platform in (0, 3) else "mac-roman")
            )
    require(expected_name in names, "font PostScript identity mismatch")
    offset, size = tables[b"OS/2"]
    require(size >= 10, "font embedding flags unavailable")
    flags = struct.unpack_from(">H", raw, offset + 8)[0]
    require(not flags & (0x2 | 0x200), "font embedding is restricted/bitmap-only")


def embed_missing_fonts(writer: PdfWriter, sources: Mapping[str, bytes]) -> list[str]:
    embedded = []
    for page in writer.pages:
        for reference in page["/Resources"]["/Font"].values():
            font = reference.get_object()
            if font["/Subtype"] == "/Type0":
                continue  # Native CID subsets are retained; independently checked.
            descriptor = font.get("/FontDescriptor")
            require(descriptor is not None, "font descriptor missing")
            descriptor = descriptor.get_object()
            if any(k in descriptor for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                continue
            name = str(font["/BaseFont"]).lstrip("/")
            require(
                name in sources
                and font["/Subtype"] == "/TrueType"
                and font.get("/Encoding") == "/WinAnsiEncoding",
                "unsupported native font embedding",
            )
            raw = sources[name]
            checked_font(raw, name)
            stream = DecodedStreamObject()
            stream.set_data(raw)
            stream[NameObject("/Length1")] = NumberObject(len(raw))
            descriptor[NameObject("/FontFile2")] = writer._add_object(stream)
            embedded.append(name)
    return sorted(set(embedded))


def preflight(
    workbook: Path,
    workbook_sha: str,
    profile: Path,
    profile_sha: str,
    document: Path,
    document_sha: str,
    *,
    allow_test_profile: bool = False,
) -> dict[str, Any]:
    paths = (workbook, profile, document, NATIVE_ENGINE, INSPECTOR, Path(__file__))
    snapshots = {p.resolve(): p.read_bytes() for p in paths}
    require(
        hashlib.sha256(snapshots[workbook.resolve()]).hexdigest() == workbook_sha,
        "XLSX SHA mismatch",
    )
    p = validator.load_json(profile, profile_sha)
    d = validator.load_json(document, document_sha)
    validator.validate_or_raise(
        workbook, p, profile_sha, d, document_sha, allow_test_profile=allow_test_profile
    )
    for binding in (
        d["approval_provenance"]["source_bindings"] + p["reference_provenance"]
    ):
        source = Path(binding["path"]).resolve()
        raw = source.read_bytes()
        sha = binding.get("sha256", binding.get("actual_sha256"))
        require(hashlib.sha256(raw).hexdigest() == sha, "PDF upstream source drift")
        snapshots[source] = raw
    return {
        "workbook": workbook.resolve(),
        "profile_path": profile.resolve(),
        "document_path": document.resolve(),
        "profile": p,
        "profile_sha": profile_sha,
        "document": d,
        "document_sha": document_sha,
        "workbook_sha": workbook_sha,
        "snapshots": snapshots,
        "allow_test_profile": allow_test_profile,
        "read_only": True,
        "production_export_authorized": False,
        "production_pdf_status": PRODUCTION_STATUS,
    }


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def recheck(plan: Mapping[str, Any]) -> None:
    for p, raw in plan["snapshots"].items():
        require(p.read_bytes() == raw, "PDF source/engine changed during export")
    # Include document source and profile provenance, not just top-level JSON.
    require(
        json.loads(plan["profile_path"].read_bytes()) == plan["profile"]
        and json.loads(plan["document_path"].read_bytes()) == plan["document"],
        "PDF preflight plan mutated",
    )
    validator.validate_or_raise(
        plan["workbook"],
        plan["profile"],
        plan["profile_sha"],
        plan["document"],
        plan["document_sha"],
        allow_test_profile=plan["allow_test_profile"],
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "duplicate source field")
        result[key] = value
    return result


def bound_json(path: Path, sha: str) -> dict[str, Any]:
    require(
        path.is_absolute() and bool(SHA_RE.fullmatch(sha)), "exact binding required"
    )
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == sha, "source SHA drift")
    value = json.loads(raw, object_pairs_hook=strict_pairs)
    require(isinstance(value, dict), "source object required")
    return value


def check_test_runtime(trust: Mapping[str, Any]) -> None:
    require(trust.get("test_only") is True, PRODUCTION_STATUS)
    require(
        set(trust)
        == {"test_only", "executable", "executable_sha256", "inspector_sha256"}
        and digest(trust["executable"]) == trust["executable_sha256"]
        and digest(INSPECTOR) == trust["inspector_sha256"],
        "TEST-ONLY runtime/inspector identity drift or invalid binding",
    )


def run_inspector(
    trust: Mapping[str, Any], pdf: Path, *, expectations_path: Path | None, timeout: int
) -> dict[str, Any]:
    check_test_runtime(trust)
    pdf_sha = digest(pdf)
    exp_sha = digest(expectations_path) if expectations_path else None
    identity = trust
    runtime_sha = identity["executable_sha256"]
    inspector_sha = identity["inspector_sha256"]
    require(
        digest(trust["executable"]) == runtime_sha
        and digest(INSPECTOR) == inspector_sha,
        "inspector/runtime pre-execution drift",
    )
    args = [
        str(trust["executable"]),
        "-I",
        "-B",
        str(INSPECTOR),
        "--pdf",
        str(pdf),
        "--pdf-sha256",
        pdf_sha,
    ]
    args += (
        ["--expectations", str(expectations_path), "--expectations-sha256", exp_sha]
        if expectations_path
        else ["--measure-clips"]
    )
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )
    require(
        completed.returncode == 0,
        "PDF independent validator HOLD: " + completed.stdout.strip(),
    )
    receipt = json.loads(completed.stdout)
    require(
        receipt["pdf_sha256"] == pdf_sha
        and receipt["expectations_sha256"] == exp_sha
        and receipt["runtime_sha256"] == runtime_sha
        and receipt["inspector_sha256"] == inspector_sha
        and digest(pdf) == pdf_sha
        and (expectations_path is None or digest(expectations_path) == exp_sha),
        "PDF inspection receipt/subject identity drift",
    )
    check_test_runtime(trust)
    return {
        **receipt,
        "inspection_scope": "TEST_ONLY",
        "production_pdf_status": PRODUCTION_STATUS,
    }


def expectations(plan: Mapping[str, Any], pages: int) -> dict[str, Any]:
    d = plan["document"]
    cells, _, _, layout = validator.expected_cells(
        plan["profile"]["presentation_contract"], d
    )
    texts = []
    items_by_row = dict(
        zip(
            [r["row"] for r in layout["rows"] if r["kind"] == "item"],
            d["items"],
            strict=True,
        )
    )
    for coordinate, value in cells.items():
        if isinstance(value, str) and value.startswith("="):
            row = int(coordinate[1:])
            if coordinate.startswith("I"):
                value = (
                    items_by_row[row]["approved_line_total_kzt"]
                    if row in items_by_row
                    else d["approved_grand_total_kzt"]
                )
            else:
                value = cells["C9"]
        texts.append(str(value))
    return {
        "page_count": pages,
        "texts": texts,
        "logo_base64": plan["profile"]["presentation_contract"]["assets"][0][
            "data_base64"
        ],
        "bindings": {
            "/DINVAWorkbookSHA256": plan["workbook_sha"],
            "/DINVAProfileSHA256": plan["profile_sha"],
            "/DINVADocumentSHA256": plan["document_sha"],
            "/DINVAClientSendAuthorized": "false",
        },
    }


def export(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Closed production API, including every legacy/cached caller signature."""
    raise ValueError(PRODUCTION_STATUS)


def _export(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Closed legacy internal entrypoint; no approval can reactivate it."""
    raise ValueError(PRODUCTION_STATUS)


def require_synthetic(plan: Mapping[str, Any], output: Path) -> None:
    require(plan.get("allow_test_profile") is True, PRODUCTION_STATUS)
    root = plan["workbook"].parent
    bindings = plan["document"]["approval_provenance"]["source_bindings"]
    source = next(
        b for b in bindings if b["role"] == "AUTHORITATIVE_DOCUMENT_TEXT_SOURCE"
    )
    data = bound_json(Path(source["path"]), source["sha256"])
    require(
        plan["allow_test_profile"] is True
        and os.environ.get("DINVA_RENDERER_TEST_MODE") == "1"
        and data["case_id"].startswith("CASE-TEST-ONLY-")
        and plan["document"]["approval_provenance"]["approval_id"] == "SYNTHETIC"
        and root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
        and all(
            plan[k].parent == root
            for k in ("workbook", "document_path", "profile_path")
        )
        and Path(source["path"]).resolve().parent == root.resolve()
        and root.resolve() != Path(tempfile.gettempdir()).resolve()
        and output.resolve().parent == root,
        PRODUCTION_STATUS + "; TEST-ONLY synthetic subjects/output required",
    )


def export_test_only(
    plan: dict[str, Any],
    output: Path,
    authorization: str,
    *,
    inspector_python: Path,
    timeout: int = 120,
) -> dict[str, Any]:
    require(
        authorization == TEST_AUTHORIZATION,
        PRODUCTION_STATUS + "; explicit TEST-ONLY authorization required",
    )
    require_synthetic(plan, output)
    trust = {
        "test_only": True,
        "executable": inspector_python.resolve(strict=True),
        "executable_sha256": digest(inspector_python),
        "inspector_sha256": digest(INSPECTOR),
    }
    return _export_test_only(plan, output, trust, timeout=timeout)


def _export_test_only(
    plan: dict[str, Any], output: Path, trust: dict[str, Any], *, timeout: int
) -> dict[str, Any]:
    require(trust.get("test_only") is True, PRODUCTION_STATUS)
    require_synthetic(plan, output)
    check_test_runtime(trust)
    path = output.resolve()
    require(
        path.suffix.lower() == ".pdf"
        and path.parent.is_dir()
        and not renderer.is_inside_project(path),
        "PDF output must be new outside-Git path",
    )
    require(not path.exists() and path not in plan["snapshots"], "PDF output collision")
    recheck(plan)
    font_root = Path(os.environ["SystemRoot"]) / "Fonts"
    fonts = {}
    for name, filename in SYSTEM_FONT_FILES.items():
        source = (font_root / filename).resolve()
        raw = source.read_bytes()
        checked_font(raw, name)
        plan["snapshots"][source] = raw
        fonts[name] = raw
    published = False
    identity = None
    with tempfile.TemporaryDirectory(
        prefix=".dinva-pdf-", dir=path.parent
    ) as temporary:
        root = Path(temporary)
        candidate = root / "candidate.pdf"
        bound = root / "bound.pdf"
        exp = root / "expectations.json"
        # The .ps1 asset denies direct execution. Decode its immutable template
        # only inside this isolated TEST-ONLY action; production is not implemented.
        template = (
            plan["snapshots"][NATIVE_ENGINE.resolve()]
            .decode("utf-8")
            .replace("\r\n", "\n")
        )
        require(
            template.startswith(NATIVE_GUARD), "native direct-execution guard missing"
        )
        payload = base64.b64encode(template[len(NATIVE_GUARD) :].encode()).decode()
        command = (
            "$wu4Native = [ScriptBlock]::Create([Text.Encoding]::UTF8.GetString("
            f"[Convert]::FromBase64String('{payload}'))); & $wu4Native "
            "-Workbook '" + str(plan["workbook"]).replace("'", "''") + "' "
            "-Output '" + str(candidate).replace("'", "''") + "'"
        )
        engine = subprocess.run(
            [
                str(
                    Path(os.environ["SystemRoot"])
                    / "System32/WindowsPowerShell/v1.0/powershell.exe"
                ),
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                base64.b64encode(command.encode("utf-16-le")).decode(),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
        receipt = json.loads(engine.stdout)
        require(
            receipt["engine"] == "MICROSOFT_EXCEL"
            and type(receipt["page_count"]) is int
            and receipt["page_count"] > 0,
            "native pagination evidence missing",
        )
        expected = expectations(plan, receipt["page_count"])
        font_stage = root / "embedded.pdf"
        font_writer = PdfWriter(clone_from=str(candidate))
        embedded_fonts = embed_missing_fonts(font_writer, fonts)
        with font_stage.open("xb") as stream:
            font_writer.write(stream)
        native_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
        geometry = run_inspector(
            trust, font_stage, expectations_path=None, timeout=timeout
        )
        require(
            geometry["status"] == "MEASURED"
            and geometry["native_pdf_sha256"]
            == hashlib.sha256(font_stage.read_bytes()).hexdigest(),
            "native geometry subject drift",
        )
        writer = PdfWriter(clone_from=str(font_stage))
        for correction in geometry["corrections"]:
            page = writer.pages[correction["page"]]
            stream = page.get_contents()
            index = correction["rectangle_op"]
            old, operation = stream.operations[index]
            require(
                operation == b"re" and [float(x) for x in old] == correction["old"],
                "native clipping path drift",
            )
            require(
                correction["new"][0] == correction["old"][0]
                and correction["new"][2] == correction["old"][2],
                "horizontal geometry change forbidden",
            )
            stream.operations[index] = (
                [FloatObject(x) for x in correction["new"]],
                operation,
            )
            page.replace_contents(stream)
        expected["bindings"]["/DINVAClipRecoverySHA256"] = hashlib.sha256(
            json.dumps(geometry, sort_keys=True).encode()
        ).hexdigest()
        expected["bindings"]["/DINVANativePDFSHA256"] = native_sha
        expected["bindings"]["/DINVAFontSourcesSHA256"] = hashlib.sha256(
            json.dumps(
                {name: hashlib.sha256(raw).hexdigest() for name, raw in fonts.items()},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        expected["bindings"]["/DINVATestOnly"] = "true"
        expected["bindings"]["/DINVAInspectorSHA256"] = digest(INSPECTOR)
        expected["bindings"]["/DINVAInspectorRuntimeSHA256"] = digest(
            trust["executable"]
        )
        expected["bindings"]["/DINVAProductionPDFStatus"] = PRODUCTION_STATUS
        writer.add_metadata(expected["bindings"])
        with bound.open("xb") as stream:
            writer.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        exp.write_text(json.dumps(expected, ensure_ascii=False), encoding="utf-8")
        result = run_inspector(trust, bound, expectations_path=exp, timeout=timeout)
        require(
            result["status"] == "PASS" and result["client_send_authorized"] is False,
            "PDF inspection HOLD",
        )
        recheck(plan)
        require_synthetic(plan, output)
        check_test_runtime(trust)
        try:
            require(
                digest(bound) == result["pdf_sha256"],
                "validated PDF changed before publication",
            )
            stat = bound.stat()
            identity = (stat.st_dev, stat.st_ino)
            os.link(bound, path)
            published = True
            stat = path.stat()
            require(
                (stat.st_dev, stat.st_ino) == identity,
                "PDF publication identity mismatch",
            )
            require(
                path.read_bytes() == bound.read_bytes()
                and digest(path) == result["pdf_sha256"],
                "PDF publication bytes mismatch",
            )
            recheck(plan)
            require_synthetic(plan, output)
            check_test_runtime(trust)
            require(
                digest(path) == result["pdf_sha256"],
                "published PDF inspection binding drift",
            )
        except BaseException:
            if published and path.exists():
                stat = path.stat()
                if (stat.st_dev, stat.st_ino) == identity:
                    path.unlink()
            raise
    return {
        **result,
        "output": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "client_send_authorized": False,
        "status": "PASS_TEST_ONLY",
        "test_only": True,
        "production_export_authorized": False,
        "production_pdf_status": PRODUCTION_STATUS,
        "measured_clip_recoveries": len(geometry["corrections"]),
        "embedded_fonts": embedded_fonts,
    }


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    # Close production intent before parsing/reading any inputs or old approvals.
    closed_flags = {
        "--export",
        "--output",
        "--approval",
        "--approval-sha256",
        "--authorization",
        "--inspector-python",
    }
    if any(value.split("=", 1)[0] in closed_flags for value in values):
        print("HOLD: " + PRODUCTION_STATUS)
        return 1
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("workbook", "profile", "document"):
        p.add_argument("--" + name, type=Path, required=True)
        p.add_argument("--" + name + "-sha256", required=True)
    p.add_argument("--export", action="store_true", help="always HOLD; deferred to WU5")
    a = p.parse_args(values)
    try:
        plan = preflight(
            a.workbook,
            a.workbook_sha256,
            a.profile,
            a.profile_sha256,
            a.document,
            a.document_sha256,
        )
        recheck(plan)
        print(
            "PDF_PREFLIGHT=PASS; READ_ONLY=true; PRODUCTION_PDF="
            + PRODUCTION_STATUS
            + "; CLIENT_SEND=CLOSED"
        )
        return 0
    except Exception as exc:
        print(f"HOLD: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
