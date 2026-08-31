from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import py_compile
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    PROJECT_ROOT / "scripts" / "publish_invoice519_yauo_enclosure_human_decision.py"
)


def load_writer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "publish_invoice519_yauo_enclosure_human_decision_for_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


writer = load_writer()


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_workbook(
    path: Path,
    cell_value: str = writer.CANONICAL_CELL_VALUE,
    sheet_name: str = writer.CANONICAL_WORKSHEET,
) -> bytes:
    workbook = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
    relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1"
  Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
  Target="worksheets/sheet1.xml"/>
</Relationships>"""
    shared_strings = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 count="1" uniqueCount="1"><si><t>{cell_value}</t></si></sst>"""
    worksheet = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
 <sheetData><row r="111"><c r="G111" t="s"><v>0</v></c></row></sheetData>
</worksheet>"""
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/sharedStrings.xml", shared_strings)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return path.read_bytes()


def synthetic_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, str]:
    path = tmp_path / "canonical-invoice519.xlsx"
    raw = write_workbook(path)
    digest = sha256(raw)
    monkeypatch.setattr(writer, "CANONICAL_WORKBOOK_PATH", path.resolve())
    monkeypatch.setattr(writer, "CANONICAL_WORKBOOK_SHA256", digest)
    return path, digest


def valid_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], Path, str]:
    path, digest = synthetic_source(tmp_path, monkeypatch)
    source = writer.load_and_validate_canonical_source(path, digest)
    payload = writer.build_payload(source, "2026-08-28T00:00:00Z")
    return payload, path, digest


def cli_arguments(source: Path, digest: str, output: Path, token: str) -> list[str]:
    return [
        "--canonical-invoice-519",
        str(source),
        "--canonical-invoice-519-sha256",
        digest,
        "--output",
        str(output),
        "--authorization",
        token,
    ]


def allow_synthetic_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(writer, "REPO_ROOT", tmp_path / "unrelated-repository")


def test_writer_and_test_compile(tmp_path: Path) -> None:
    py_compile.compile(str(SCRIPT), cfile=str(tmp_path / "writer.pyc"), doraise=True)
    py_compile.compile(
        str(Path(__file__)), cfile=str(tmp_path / "test.pyc"), doraise=True
    )


def test_positive_exact_decision_and_immutable_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload, source, digest = valid_payload(tmp_path, monkeypatch)
    assert payload["project_id"] == "2024/086"
    assert payload["invoice_number"] == 519
    assert payload["technical_decision"] == writer.TECHNICAL_DECISION
    assert payload["source_binding"]["worksheet"] == "Лист1"
    assert payload["source_binding"]["cell"] == "G111"
    assert {name for name, value in payload["safety"].items() if value} == {
        "human_decision_recorded",
        "technical_decision_recorded",
    }
    allow_synthetic_output(tmp_path, monkeypatch)
    output = tmp_path / "new-decision" / writer.OUTPUT_FILENAME
    assert (
        writer.main(
            cli_arguments(source, digest, output, writer.PUBLICATION_AUTHORIZATION)
        )
        == 0
    )
    assert "PUBLISHED_IMMUTABLE_NO_OVERWRITE" in capsys.readouterr().out
    assert list(output.parent.iterdir()) == [output]
    published = json.loads(output.read_text(encoding="utf-8"))
    writer.validate_payload(published)


def test_authorization_fails_before_any_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, digest = synthetic_source(tmp_path, monkeypatch)
    output = tmp_path / "new-decision" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="publication authorization"):
        writer.main(cli_arguments(source, digest, output, "WRONG"))
    assert not output.parent.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project_id", "2024/087"),
        ("invoice_number", 520),
        ("technical_decision.invoice_position_number", 88),
        ("technical_decision.product_identity", "YAUO_OTHER"),
        ("technical_decision.previous_value", "451×300×250 mm"),
        ("technical_decision.approved_value", "400×301×250 mm"),
    ],
)
def test_wrong_identity_or_dimensions_fail_closed(
    field: str,
    value: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, _source, _digest = valid_payload(tmp_path, monkeypatch)
    if field.startswith("technical_decision."):
        payload["technical_decision"][field.split(".", 1)[1]] = value
    else:
        payload[field] = value
    with pytest.raises(writer.ContractError, match="schema const|technical decision"):
        writer.validate_payload(payload)


def test_canonical_source_path_binding_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, digest = synthetic_source(tmp_path, monkeypatch)
    wrong = tmp_path / "wrong.xlsx"
    wrong.write_bytes(source.read_bytes())
    with pytest.raises(writer.ContractError, match="path binding mismatch"):
        writer.load_and_validate_canonical_source(wrong, digest)


@pytest.mark.parametrize("bad_sha", ["0" * 64, "A" * 64, "short"])
def test_canonical_source_sha_binding_fails_closed(
    bad_sha: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _digest = synthetic_source(tmp_path, monkeypatch)
    with pytest.raises(writer.ContractError, match="SHA"):
        writer.load_and_validate_canonical_source(source, bad_sha)


def test_canonical_source_actual_sha_drift_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, digest = synthetic_source(tmp_path, monkeypatch)
    source.write_bytes(source.read_bytes() + b"drift")
    with pytest.raises(writer.ContractError, match="initial SHA mismatch"):
        writer.load_and_validate_canonical_source(source, digest)


@pytest.mark.parametrize(
    ("cell_value", "sheet_name", "message"),
    [
        ("Накладной 400х300х250 металл 1,2мм", "Лист1", "cell value"),
        (writer.CANONICAL_CELL_VALUE, "Other", "worksheet binding"),
    ],
)
def test_canonical_source_cell_or_sheet_drift_fails_closed(
    cell_value: str,
    sheet_name: str,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "canonical.xlsx"
    raw = write_workbook(source, cell_value, sheet_name)
    digest = sha256(raw)
    monkeypatch.setattr(writer, "CANONICAL_WORKBOOK_PATH", source.resolve())
    monkeypatch.setattr(writer, "CANONICAL_WORKBOOK_SHA256", digest)
    with pytest.raises(writer.ContractError, match=message):
        writer.load_and_validate_canonical_source(source, digest)


def test_schema_is_strict_and_extra_keys_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, _source, _digest = valid_payload(tmp_path, monkeypatch)
    schema = writer.load_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["technical_decision"]["const"] == (
        writer.TECHNICAL_DECISION
    )
    payload["quote"] = {}
    with pytest.raises(writer.ContractError, match="schema extra keys"):
        writer.validate_payload(payload)


@pytest.mark.parametrize(
    "field_name",
    [field_name for field_name, value in writer.SAFETY.items() if not value],
)
def test_every_downstream_flag_remains_closed(
    field_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, _source, _digest = valid_payload(tmp_path, monkeypatch)
    payload["safety"][field_name] = True
    with pytest.raises(writer.ContractError, match="schema const|safety boundary"):
        writer.validate_payload(payload)


def test_bad_timestamp_and_duplicate_json_key_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _payload, source, digest = valid_payload(tmp_path, monkeypatch)
    loaded = writer.load_and_validate_canonical_source(source, digest)
    with pytest.raises(writer.ContractError, match="created_at_utc format"):
        writer.build_payload(loaded, "not-a-time")
    with pytest.raises(writer.ContractError, match="strict JSON"):
        writer.load_json_bytes(b'{"a": 1, "a": 2}', "duplicate test")


def test_output_collision_name_and_repository_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, digest = synthetic_source(tmp_path, monkeypatch)
    inside = PROJECT_ROOT / ".yauo-decision-runtime" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="outside repository"):
        writer.publish_decision(source, digest, inside)
    assert not inside.parent.exists()
    existing = tmp_path / "existing" / writer.OUTPUT_FILENAME
    existing.parent.mkdir()
    with pytest.raises(writer.ContractError, match="directory already exists"):
        writer.publish_decision(source, digest, existing)
    wrong_name = tmp_path / "new" / "wrong.json"
    with pytest.raises(writer.ContractError, match="filename mismatch"):
        writer.publish_decision(source, digest, wrong_name)


def test_toctou_change_rolls_back_staging_and_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, digest = synthetic_source(tmp_path, monkeypatch)
    original_read = Path.read_bytes
    source_reads = 0

    def change_on_reread(path: Path) -> bytes:
        nonlocal source_reads
        raw = original_read(path)
        if path == source.resolve():
            source_reads += 1
            if source_reads == 2:
                return raw + b"changed"
        return raw

    monkeypatch.setattr(Path, "read_bytes", change_on_reread)
    allow_synthetic_output(tmp_path, monkeypatch)
    output = tmp_path / "new-decision" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="TOCTOU"):
        writer.publish_decision(source, digest, output)
    assert not output.exists()
    assert not output.parent.exists()


def test_post_link_failure_rolls_back_final_staging_and_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, digest = synthetic_source(tmp_path, monkeypatch)
    original_link = writer.os.link
    original_validate = writer.validate_payload
    linked = False

    def observed_link(staging: Path, output: Path) -> None:
        nonlocal linked
        original_link(staging, output)
        linked = True

    def fail_after_link(payload: dict[str, Any]) -> None:
        original_validate(payload)
        if linked:
            raise writer.ContractError("synthetic post-link failure")

    monkeypatch.setattr(writer.os, "link", observed_link)
    monkeypatch.setattr(writer, "validate_payload", fail_after_link)
    allow_synthetic_output(tmp_path, monkeypatch)
    output = tmp_path / "new-decision" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="synthetic post-link"):
        writer.publish_decision(source, digest, output)
    assert linked is True
    assert not output.exists()
    assert not output.parent.exists()


def test_source_contains_no_quote_generator_or_external_actions() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])
    assert "subprocess" not in imported
    assert "run_invoice_quote" not in source
    assert "fill_invoice_quote" not in source
    assert writer.PUBLICATION_AUTHORIZATION.endswith("PUBLICATION_AUTHORIZED")
