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

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "publish_invoice519_price_application.py"


def load_writer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "publish_invoice519_price_application_for_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


writer = load_writer()


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def completed_input() -> dict[str, Any]:
    return {
        "schema_version": "price_calculator_input_draft.v0.2",
        "safety": {
            "price_approved_by_igor": False,
            "production_authorized": False,
            "downstream_started": False,
            "sending_authorized": False,
            "commercial_csv_authorized": False,
        },
    }


def pricing_profile() -> dict[str, Any]:
    return {
        "schema_version": "technical_invoice519_pricing_profile_human_decisions.v0.1",
        "status": "IGOR_INVOICE519_PRICING_PROFILE_APPROVED_NOT_APPLIED",
        "application_status": "NOT_APPLIED",
        "positions": [
            {"invoice_position_number": position}
            for position in writer.predecessor.FROZEN_55_POSITIONS
        ],
    }


def synthetic_predecessor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, str, dict[str, Any]]:
    predecessor = writer.predecessor
    values: dict[str, bytes] = {
        "completed_technical_input": encoded(completed_input()),
        "main_price_workbook": b"synthetic main workbook",
        "custom_sche_metal_workbook": b"synthetic metal workbook",
        "pricing_profile": encoded(pricing_profile()),
        "canonical_invoice_519": b"synthetic canonical invoice",
        "ukrm_price_workbook": b"synthetic ukrm workbook",
        "yarv100_price_workbook": b"synthetic yarv workbook",
    }
    paths: dict[str, Path] = {}
    specs: list[Any] = []
    for original in predecessor.INPUT_SPECS:
        suffix = (
            ".json" if original.media_type == predecessor.JSON_MEDIA_TYPE else ".xlsx"
        )
        path = tmp_path / f"{original.role}{suffix}"
        raw = values[original.role]
        path.write_bytes(raw)
        paths[original.role] = path
        specs.append(
            predecessor.InputSpec(
                original.role,
                str(path.resolve()),
                sha256(raw),
                original.media_type,
            )
        )
    monkeypatch.setattr(predecessor, "INPUT_SPECS", tuple(specs))
    shas = {spec.role: spec.sha256 for spec in specs}
    loaded = predecessor.load_and_validate_inputs(paths, shas)
    payload = predecessor.build_payload(loaded, "2026-08-27T00:00:00Z")
    raw = encoded(payload)
    path = tmp_path / predecessor.OUTPUT_FILENAME
    path.write_bytes(raw)
    digest = sha256(raw)
    monkeypatch.setattr(writer, "PREDECESSOR_PATH", path.resolve())
    monkeypatch.setattr(writer, "PREDECESSOR_SHA256", digest)
    return path, digest, payload


def rewrite_predecessor(
    path: Path, payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> str:
    raw = encoded(payload)
    path.write_bytes(raw)
    digest = sha256(raw)
    monkeypatch.setattr(writer, "PREDECESSOR_SHA256", digest)
    return digest


def cli_arguments(
    predecessor_path: Path, predecessor_sha: str, output: Path, authorization: str
) -> list[str]:
    return [
        "--price-human-decision",
        str(predecessor_path),
        "--price-human-decision-sha256",
        predecessor_sha,
        "--output",
        str(output),
        "--authorization",
        authorization,
    ]


def valid_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], Path, str]:
    path, digest, _source = synthetic_predecessor(tmp_path, monkeypatch)
    loaded = writer.load_and_validate_predecessor(path, digest)
    payload = writer.build_payload(loaded, "2026-08-27T01:00:00Z")
    return payload, path, digest


def allow_synthetic_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(writer, "REPO_ROOT", tmp_path / "unrelated-repo-root")


def test_writer_and_test_py_compile(tmp_path: Path) -> None:
    py_compile.compile(str(SCRIPT), cfile=str(tmp_path / "writer.pyc"), doraise=True)
    py_compile.compile(
        str(Path(__file__)), cfile=str(tmp_path / "test.pyc"), doraise=True
    )


def test_positive_payload_and_immutable_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload, predecessor_path, digest = valid_payload(tmp_path, monkeypatch)
    assert payload["status"] == "IGOR_INVOICE519_PRICE_APPLIED_QUOTE_NOT_GENERATED"
    assert payload["price_application"] == writer.PRICE_APPLICATION
    assert payload["reconciliation"]["coverage"] == {
        "covered": 88,
        "total": 88,
        "overlap": 0,
        "uncovered": 0,
    }
    assert payload["technical_composition"]["status"] == "UNCHANGED_FROM_PREDECESSOR"
    assert {key for key, value in payload["safety"].items() if value} == {
        "human_decision_recorded",
        "price_approved",
        "price_application_authorized",
        "price_applied",
    }
    allow_synthetic_output(tmp_path, monkeypatch)
    output = tmp_path / "new-application" / writer.OUTPUT_FILENAME
    assert (
        writer.main(
            cli_arguments(
                predecessor_path, digest, output, writer.PUBLICATION_AUTHORIZATION
            )
        )
        == 0
    )
    report = capsys.readouterr().out
    assert "PUBLISHED_IMMUTABLE_NO_OVERWRITE" in report
    assert output.is_file()
    assert list(output.parent.iterdir()) == [output]
    published = json.loads(output.read_text(encoding="utf-8"))
    writer.validate_payload(published)


def test_authorization_fails_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    predecessor_path, digest, _payload = synthetic_predecessor(tmp_path, monkeypatch)
    output = tmp_path / "new-application" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="publication authorization"):
        writer.main(cli_arguments(predecessor_path, digest, output, "WRONG"))
    assert not output.parent.exists()


def test_wrong_predecessor_path_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    predecessor_path, digest, _payload = synthetic_predecessor(tmp_path, monkeypatch)
    wrong = tmp_path / "wrong-predecessor.json"
    wrong.write_bytes(predecessor_path.read_bytes())
    with pytest.raises(writer.ContractError, match="path binding mismatch"):
        writer.load_and_validate_predecessor(wrong, digest)


@pytest.mark.parametrize("bad_sha", ["0" * 64, "A" * 64, "x"])
def test_wrong_or_malformed_sha_fails_closed(
    bad_sha: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    predecessor_path, _digest, _payload = synthetic_predecessor(tmp_path, monkeypatch)
    with pytest.raises(writer.ContractError, match="SHA"):
        writer.load_and_validate_predecessor(predecessor_path, bad_sha)


@pytest.mark.parametrize("mutation", ["status", "price", "reconciliation", "safety"])
def test_predecessor_contract_drift_fails_closed(
    mutation: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    predecessor_path, _digest, payload = synthetic_predecessor(tmp_path, monkeypatch)
    if mutation == "status":
        payload["status"] = "APPLIED"
    elif mutation == "price":
        payload["price_approval"]["approved_price_kzt"] += 1
    elif mutation == "reconciliation":
        payload["reconciliation"]["coverage"]["uncovered"] = 1
    else:
        payload["safety"]["quote_generation_authorized"] = True
    digest = rewrite_predecessor(predecessor_path, payload, monkeypatch)
    with pytest.raises(writer.ContractError, match="predecessor contract mismatch"):
        writer.load_and_validate_predecessor(predecessor_path, digest)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("price", "schema const|price application"),
        ("reconciliation", "schema const|reconciliation"),
        ("technical", "technical composition drift"),
        ("source_binding", "actual SHA mismatch"),
        ("predecessor_binding", "expected SHA"),
    ],
)
def test_successor_contract_drift_fails_closed(
    mutation: str,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, _predecessor_path, _digest = valid_payload(tmp_path, monkeypatch)
    if mutation == "price":
        payload["price_application"]["applied_price_kzt"] += 1
    elif mutation == "reconciliation":
        payload["reconciliation"]["coverage"]["overlap"] = 1
    elif mutation == "technical":
        payload["technical_composition"]["path"] += ".changed"
    elif mutation == "source_binding":
        payload["source_input_bindings"][0]["actual_sha256"] = "0" * 64
    else:
        payload["predecessor"]["expected_sha256"] = "0" * 64
    with pytest.raises(writer.ContractError, match=message):
        writer.validate_payload(payload)


@pytest.mark.parametrize(
    "field_name",
    [field_name for field_name, value in writer.SAFETY.items() if not value],
)
def test_every_closed_safety_flag_fails_if_enabled(
    field_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, _predecessor_path, _digest = valid_payload(tmp_path, monkeypatch)
    payload["safety"][field_name] = True
    with pytest.raises(writer.ContractError, match="schema const|safety boundary"):
        writer.validate_payload(payload)


@pytest.mark.parametrize(
    "field_name",
    [field_name for field_name, value in writer.SAFETY.items() if value],
)
def test_every_required_true_safety_flag_fails_if_disabled(
    field_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, _predecessor_path, _digest = valid_payload(tmp_path, monkeypatch)
    payload["safety"][field_name] = False
    with pytest.raises(writer.ContractError, match="schema const|safety boundary"):
        writer.validate_payload(payload)


def test_extra_field_and_bad_created_at_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, predecessor_path, digest = valid_payload(tmp_path, monkeypatch)
    payload["quote"] = {}
    with pytest.raises(writer.ContractError, match="schema extra keys"):
        writer.validate_payload(payload)
    loaded = writer.load_and_validate_predecessor(predecessor_path, digest)
    with pytest.raises(writer.ContractError, match="created_at_utc format"):
        writer.build_payload(loaded, "not-a-timestamp")


def test_output_policy_is_outside_repo_and_no_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    predecessor_path, digest, _payload = synthetic_predecessor(tmp_path, monkeypatch)
    inside_repo = (
        PROJECT_ROOT / ".price-application-runtime-test" / writer.OUTPUT_FILENAME
    )
    with pytest.raises(writer.ContractError, match="outside repository"):
        writer.publish_application(predecessor_path, digest, inside_repo)
    assert not inside_repo.parent.exists()
    existing = tmp_path / "existing" / writer.OUTPUT_FILENAME
    existing.parent.mkdir()
    with pytest.raises(writer.ContractError, match="output directory already exists"):
        writer.publish_application(predecessor_path, digest, existing)
    wrong_name = tmp_path / "new-output" / "wrong.json"
    with pytest.raises(writer.ContractError, match="output filename mismatch"):
        writer.publish_application(predecessor_path, digest, wrong_name)


def test_toctou_change_rolls_back_staging_and_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    predecessor_path, digest, _payload = synthetic_predecessor(tmp_path, monkeypatch)
    original_read_bytes = Path.read_bytes
    target_reads = 0

    def changed_on_reread(path: Path) -> bytes:
        nonlocal target_reads
        raw = original_read_bytes(path)
        if path == predecessor_path.resolve():
            target_reads += 1
            if target_reads == 2:
                return raw + b"changed"
        return raw

    monkeypatch.setattr(Path, "read_bytes", changed_on_reread)
    allow_synthetic_output(tmp_path, monkeypatch)
    output = tmp_path / "new-application" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="TOCTOU"):
        writer.publish_application(predecessor_path, digest, output)
    assert not output.exists()
    assert not output.parent.exists()


def test_post_link_validation_failure_rolls_back_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    predecessor_path, digest, _payload = synthetic_predecessor(tmp_path, monkeypatch)
    original_link = writer.os.link
    original_validate = writer.validate_payload
    link_completed = False

    def observed_link(source: Path, destination: Path) -> None:
        nonlocal link_completed
        original_link(source, destination)
        link_completed = True

    def fail_only_after_link(payload: dict[str, Any]) -> None:
        original_validate(payload)
        if link_completed:
            raise writer.ContractError("synthetic post-link validation failure")

    monkeypatch.setattr(writer.os, "link", observed_link)
    monkeypatch.setattr(writer, "validate_payload", fail_only_after_link)
    allow_synthetic_output(tmp_path, monkeypatch)
    output = tmp_path / "new-application" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="synthetic post-link"):
        writer.publish_application(predecessor_path, digest, output)
    assert link_completed is True
    assert not output.exists()
    assert not output.parent.exists()


def test_schema_and_source_are_closed_and_downstream_free() -> None:
    schema = writer.load_schema()
    assert schema["additionalProperties"] is False
    properties = schema["properties"]
    assert properties["schema_version"]["const"] == writer.SCHEMA_VERSION
    assert properties["status"]["const"] == writer.STATUS
    assert properties["application_scope"]["const"] == "PRICE_ONLY"
    assert properties["application_status"]["const"] == "APPLIED"
    assert properties["price_application"]["const"] == writer.PRICE_APPLICATION
    assert properties["safety"]["const"] == writer.SAFETY
    assert (
        writer.PUBLICATION_AUTHORIZATION != writer.predecessor.PUBLICATION_AUTHORIZATION
    )

    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])
    assert imported <= {
        "__future__",
        "argparse",
        "copy",
        "hashlib",
        "importlib",
        "json",
        "os",
        "re",
        "sys",
        "tempfile",
        "collections",
        "dataclasses",
        "datetime",
        "pathlib",
        "types",
        "typing",
    }
    assert "subprocess" not in imported
    assert "run_invoice_quote" not in source
    assert "checked_clientize" not in source
