from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import struct
import sys
import zlib
from pathlib import Path
from types import ModuleType
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    PROJECT_ROOT / "scripts" / "publish_dinva_classic_canonical_logo_human_decision.py"
)


def load_writer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "publish_dinva_classic_canonical_logo_human_decision_for_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


writer = load_writer()


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def make_png(width: int, height: int, mode: str) -> bytes:
    color_type = 2 if mode == "RGB" else 6
    bytes_per_pixel = 3 if mode == "RGB" else 4
    rows = bytearray()
    for row in range(height):
        rows.append(0)
        for column in range(width):
            rows.extend(
                (
                    (column * 41 + 10) & 0xFF,
                    (row * 53 + 20) & 0xFF,
                    ((row + column) * 29 + 30) & 0xFF,
                )
            )
            if bytes_per_pixel == 4:
                rows.append((row * 37 + column * 17 + 90) & 0xFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
        + png_chunk(b"IEND", b"")
    )


def write_workbook(path: Path, logo: bytes) -> bytes:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(writer.MEDIA_PART_PATH, logo)
    return path.read_bytes()


def fingerprint(logo: bytes) -> tuple[tuple[int, int], str, str]:
    dimensions, mode, rgba = writer.decode_png_rgba(logo)
    return dimensions, mode, writer.normalized_pixel_fingerprint(dimensions, rgba)


def synthetic_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[Any], list[Any]]:
    family_logo = make_png(3, 2, "RGB")
    runtime_logo = make_png(2, 3, "RGBA")
    family_dimensions, family_mode, family_fingerprint = fingerprint(family_logo)
    runtime_dimensions, runtime_mode, runtime_fingerprint = fingerprint(runtime_logo)
    specs: list[Any] = []
    inputs: list[Any] = []
    source_data = [
        ("Invoice519", "CLASSIC_FAMILY_EVIDENCE", family_logo),
        ("Invoice463", "CLASSIC_FAMILY_EVIDENCE", family_logo),
        ("Invoice551", "CLASSIC_FAMILY_EVIDENCE", family_logo),
        (
            "capacity100_tuned_v4",
            "CERTIFIED_RUNTIME_TEMPLATE_EVIDENCE",
            runtime_logo,
        ),
    ]
    for label, role, logo in source_data:
        path = tmp_path / f"{label}.xlsx"
        workbook_raw = write_workbook(path, logo)
        dimensions, mode, pixel_fingerprint = fingerprint(logo)
        spec = writer.SourceSpec(
            label,
            role,
            path.resolve(),
            sha256(workbook_raw),
            sha256(logo),
            pixel_fingerprint,
            dimensions,
            mode,
        )
        specs.append(spec)
        inputs.append(writer.SourceInput(path, spec.workbook_sha256))
    monkeypatch.setattr(writer, "SOURCE_SPECS", tuple(specs))
    canonical_decision = copy.deepcopy(writer.CANONICAL_LOGO_DECISION)
    canonical_decision.update(
        {
            "raw_sha256": sha256(family_logo),
            "normalized_pixel_fingerprint": family_fingerprint,
            "native_dimensions": list(family_dimensions),
            "decoded_mode": family_mode,
        }
    )
    monkeypatch.setattr(writer, "CANONICAL_LOGO_DECISION", canonical_decision)
    runtime_policy = copy.deepcopy(writer.RUNTIME_TEMPLATE_POLICY)
    runtime_policy["differing_logo_raw_sha256"] = sha256(runtime_logo)
    monkeypatch.setattr(writer, "RUNTIME_TEMPLATE_POLICY", runtime_policy)
    assert runtime_dimensions == (2, 3)
    assert runtime_mode == "RGBA"
    assert runtime_fingerprint != family_fingerprint
    return specs, inputs


def valid_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], list[Any], list[Any]]:
    specs, inputs = synthetic_sources(tmp_path, monkeypatch)
    loaded = writer.load_and_validate_sources(inputs)
    payload = writer.build_payload(loaded, "2026-09-01T00:00:00Z")
    return payload, specs, inputs


def allow_synthetic_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(writer, "REPO_ROOT", tmp_path / "unrelated-repository")


def cli_arguments(inputs: list[Any], output: Path, token: str) -> list[str]:
    return [
        "--invoice-519",
        str(inputs[0].path),
        "--invoice-519-sha256",
        inputs[0].expected_sha256,
        "--invoice-463",
        str(inputs[1].path),
        "--invoice-463-sha256",
        inputs[1].expected_sha256,
        "--invoice-551",
        str(inputs[2].path),
        "--invoice-551-sha256",
        inputs[2].expected_sha256,
        "--runtime-template",
        str(inputs[3].path),
        "--runtime-template-sha256",
        inputs[3].expected_sha256,
        "--output",
        str(output),
        "--authorization",
        token,
    ]


def test_positive_publication_is_exact_immutable_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload, _specs, inputs = valid_payload(tmp_path, monkeypatch)
    assert payload["schema_version"] == writer.SCHEMA_VERSION
    assert payload["status"] == writer.STATUS
    assert payload["approval_scope"] == "BRAND_LOGO_ONLY"
    assert payload["canonical_logo_application_status"] == "NOT_APPLIED_TO_PROFILE"
    assert payload["canonical_logo_decision"] == writer.CANONICAL_LOGO_DECISION
    assert payload["runtime_template_policy"] == writer.RUNTIME_TEMPLATE_POLICY
    assert {item["role"] for item in payload["source_bindings"]} == {
        "CLASSIC_FAMILY_EVIDENCE",
        "CERTIFIED_RUNTIME_TEMPLATE_EVIDENCE",
    }
    allow_synthetic_output(tmp_path, monkeypatch)
    output = tmp_path / "new-decision" / writer.OUTPUT_FILENAME
    assert (
        writer.main(cli_arguments(inputs, output, writer.PUBLICATION_AUTHORIZATION))
        == 0
    )
    assert "PUBLISHED_IMMUTABLE_NO_OVERWRITE" in capsys.readouterr().out
    assert list(output.parent.iterdir()) == [output]
    published = json.loads(output.read_text(encoding="utf-8"))
    writer.validate_payload(published)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "raw_sha256",
            "0" * 64,
            "canonical logo decision mismatch",
        ),
        (
            "normalized_pixel_fingerprint",
            "1" * 64,
            "canonical logo decision mismatch",
        ),
    ],
)
def test_wrong_canonical_raw_sha_or_normalized_fingerprint_fails_closed(
    field: str,
    value: str,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, _specs, _inputs = valid_payload(tmp_path, monkeypatch)
    payload["canonical_logo_decision"][field] = value
    with pytest.raises(writer.ContractError, match=message):
        writer.validate_payload(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("role", "CERTIFIED_RUNTIME_TEMPLATE_EVIDENCE"),
        ("path", "C:\\wrong\\source.xlsx"),
        ("expected_workbook_sha256", "2" * 64),
        ("actual_logo_raw_sha256", "3" * 64),
    ],
)
def test_wrong_source_role_path_or_sha_fails_closed(
    field: str,
    value: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, _specs, _inputs = valid_payload(tmp_path, monkeypatch)
    payload["source_bindings"][0][field] = value
    with pytest.raises(writer.ContractError, match="source bindings exact contract"):
        writer.validate_payload(payload)


def test_source_input_path_and_sha_are_exactly_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _payload, specs, inputs = valid_payload(tmp_path, monkeypatch)
    wrong_path = tmp_path / "wrong.xlsx"
    wrong_path.write_bytes(inputs[0].path.read_bytes())
    with pytest.raises(writer.ContractError, match="path binding"):
        writer.load_and_validate_source(
            writer.SourceInput(wrong_path, specs[0].workbook_sha256), specs[0]
        )
    with pytest.raises(writer.ContractError, match="SHA binding"):
        writer.load_and_validate_source(
            writer.SourceInput(inputs[0].path, "0" * 64), specs[0]
        )


def test_duplicate_keys_and_non_utf8_fail_closed() -> None:
    with pytest.raises(writer.ContractError, match="strict JSON"):
        writer.load_json_bytes(b'{"status": 1, "status": 2}', "duplicate test")
    with pytest.raises(writer.ContractError, match="strict UTF-8"):
        writer.load_json_bytes(b'{"status":"\xff"}', "encoding test")


def test_closed_schema_rejects_extra_and_missing_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, _specs, _inputs = valid_payload(tmp_path, monkeypatch)
    extra = copy.deepcopy(payload)
    extra["profile_approval"] = True
    with pytest.raises(writer.ContractError, match="schema extra keys"):
        writer.validate_payload(extra)
    missing = copy.deepcopy(payload)
    del missing["status"]
    with pytest.raises(writer.ContractError, match="schema missing keys"):
        writer.validate_payload(missing)


def test_no_overwrite_and_authorization_fail_before_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _payload, _specs, inputs = valid_payload(tmp_path, monkeypatch)
    allow_synthetic_output(tmp_path, monkeypatch)
    existing_parent = tmp_path / "existing"
    existing_parent.mkdir()
    output = existing_parent / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="directory already exists"):
        writer.publish_decision(inputs, output)
    new_output = tmp_path / "not-authorized" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="publication authorization"):
        writer.main(cli_arguments(inputs, new_output, "WRONG"))
    assert not new_output.parent.exists()


def test_toctou_change_rolls_back_staging_and_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _payload, _specs, inputs = valid_payload(tmp_path, monkeypatch)
    original_read = Path.read_bytes
    target = inputs[0].path.resolve()
    target_reads = 0

    def change_on_reread(path: Path) -> bytes:
        nonlocal target_reads
        raw = original_read(path)
        if path.resolve() == target:
            target_reads += 1
            if target_reads == 2:
                return raw + b"changed"
        return raw

    monkeypatch.setattr(Path, "read_bytes", change_on_reread)
    allow_synthetic_output(tmp_path, monkeypatch)
    output = tmp_path / "toctou" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="TOCTOU"):
        writer.publish_decision(inputs, output)
    assert not output.exists()
    assert not output.parent.exists()


@pytest.mark.parametrize(
    "field_name",
    [field for field, value in writer.SAFETY.items() if value is False],
)
def test_every_safety_authorization_remains_closed(
    field_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, _specs, _inputs = valid_payload(tmp_path, monkeypatch)
    payload["safety"][field_name] = True
    with pytest.raises(writer.ContractError, match="schema const|safety boundary"):
        writer.validate_payload(payload)


def test_publisher_is_isolated_from_renderer_profile_and_external_actions() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])
    assert "subprocess" not in imported
    assert "requests" not in imported
    assert "render_dinva_classic_quote_invoice" not in source
    assert "extract_dinva_classic_presentation_profile" not in source
    assert writer.PUBLICATION_AUTHORIZATION.endswith("PUBLICATION_AUTHORIZED")
