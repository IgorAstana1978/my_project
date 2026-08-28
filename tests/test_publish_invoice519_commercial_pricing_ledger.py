from __future__ import annotations

import ast
import copy
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
SCRIPT = PROJECT_ROOT / "scripts" / "publish_invoice519_commercial_pricing_ledger.py"


def load_writer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "publish_invoice519_commercial_pricing_ledger_under_test", SCRIPT
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


def application_payload() -> dict[str, Any]:
    application = writer.application
    return {
        "schema_version": application.SCHEMA_VERSION,
        "application_id": application.APPLICATION_ID,
        "status": application.STATUS,
        "application_scope": "PRICE_ONLY",
        "application_status": "APPLIED",
        "source_input_bindings": [
            {
                "role": spec.role,
                "path": spec.path,
                "expected_sha256": spec.sha256,
                "actual_sha256": spec.sha256,
                "media_type": spec.media_type,
            }
            for spec in application.predecessor.INPUT_SPECS
        ],
        "price_application": copy.deepcopy(application.PRICE_APPLICATION),
        "reconciliation": application.predecessor._reconciliation_payload(),
        "technical_composition": application._technical_composition(),
        "safety": copy.deepcopy(application.SAFETY),
    }


def synthetic_predecessor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, str, dict[str, Any]]:
    monkeypatch.setattr(writer.application, "validate_payload", lambda _value: None)
    payload = application_payload()
    raw = encoded(payload)
    path = tmp_path / writer.application.OUTPUT_FILENAME
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


def valid_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], Path, str]:
    path, digest, _source = synthetic_predecessor(tmp_path, monkeypatch)
    loaded = writer.load_and_validate_predecessor(path, digest)
    payload = writer.build_payload(loaded, "2026-08-28T01:00:00Z")
    return payload, path, digest


def cli_arguments(
    predecessor_path: Path,
    predecessor_sha: str,
    output: Path,
    authorization: str,
) -> list[str]:
    return [
        "--price-application",
        str(predecessor_path),
        "--price-application-sha256",
        predecessor_sha,
        "--output",
        str(output),
        "--authorization",
        authorization,
    ]


def allow_synthetic_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(writer, "REPO_ROOT", tmp_path / "unrelated-repo-root")


def test_writer_and_test_py_compile(tmp_path: Path) -> None:
    py_compile.compile(str(SCRIPT), cfile=str(tmp_path / "writer.pyc"), doraise=True)
    py_compile.compile(
        str(Path(__file__)), cfile=str(tmp_path / "test.pyc"), doraise=True
    )


def test_positive_88_position_payload_and_immutable_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload, predecessor_path, digest = valid_payload(tmp_path, monkeypatch)
    positions = payload["positions"]
    assert payload["status"] == writer.STATUS
    assert len(positions) == 88
    assert [item["invoice_position_number"] for item in positions] == list(range(1, 89))
    assert sum(item["approved_position_total_kzt"] for item in positions) == 19_499_186
    assert payload["ledger_summary"] == writer._ledger_summary()
    assert payload["price_grain"] == writer.PRICE_GRAIN
    assert payload["safety"] == writer.SAFETY
    assert "lead_time" not in payload
    assert "document_style" not in payload

    allow_synthetic_output(tmp_path, monkeypatch)
    output = tmp_path / "new-ledger" / writer.OUTPUT_FILENAME
    assert (
        writer.main(
            cli_arguments(
                predecessor_path,
                digest,
                output,
                writer.PUBLICATION_AUTHORIZATION,
            )
        )
        == 0
    )
    assert "PUBLISHED_IMMUTABLE_NO_OVERWRITE" in capsys.readouterr().out
    assert list(output.parent.iterdir()) == [output]
    published = json.loads(output.read_text(encoding="utf-8"))
    writer.validate_payload(published)


def test_exact_evidence_membership_subtotals_and_references() -> None:
    positions = writer._positions_payload()
    frozen = [
        item
        for item in positions
        if item["pricing_provenance"]["partition"] == "FROZEN_55"
    ]
    missing = [
        item
        for item in positions
        if item["pricing_provenance"]["partition"] == "CHECKED_MISSING_33"
    ]
    assert len(frozen) == 55
    assert len(missing) == 33
    assert sum(item["approved_position_total_kzt"] for item in frozen) == 11_963_792
    assert sum(item["approved_position_total_kzt"] for item in missing) == 7_535_394
    assert len(writer.CANONICAL_DATA_ROWS) == 88
    assert writer.CANONICAL_DATA_ROWS[0] == 17
    assert writer.CANONICAL_DATA_ROWS[-1] == 112
    assert all(
        item["quantity"] * item["approved_unit_price_kzt"]
        == item["approved_position_total_kzt"]
        for item in positions
    )
    assert {item["pricing_provenance"]["source_binding_role"] for item in missing} == {
        "main_price_workbook",
        "ukrm_price_workbook",
        "yarv100_price_workbook",
    }


def test_authorization_fails_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    predecessor_path, digest, _payload = synthetic_predecessor(tmp_path, monkeypatch)
    output = tmp_path / "new-ledger" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="publication authorization"):
        writer.main(cli_arguments(predecessor_path, digest, output, "WRONG"))
    assert not output.parent.exists()


def test_wrong_path_and_sha_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    predecessor_path, digest, _payload = synthetic_predecessor(tmp_path, monkeypatch)
    wrong = tmp_path / "wrong.json"
    wrong.write_bytes(predecessor_path.read_bytes())
    with pytest.raises(writer.ContractError, match="path binding mismatch"):
        writer.load_and_validate_predecessor(wrong, digest)
    with pytest.raises(writer.ContractError, match="SHA binding mismatch"):
        writer.load_and_validate_predecessor(predecessor_path, "0" * 64)
    with pytest.raises(writer.ContractError, match="SHA format"):
        writer.load_and_validate_predecessor(predecessor_path, "BAD")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("schema", "schema"),
        ("id", "ID"),
        ("status", "status"),
        ("scope", "scope"),
        ("application", "application status"),
        ("price", "applied price"),
        ("reconciliation", "reconciliation"),
        ("technical", "technical composition"),
        ("safety", "predecessor safety"),
    ],
)
def test_predecessor_contract_drift_fails_closed(
    mutation: str,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, _digest, payload = synthetic_predecessor(tmp_path, monkeypatch)
    if mutation == "schema":
        payload["schema_version"] = "wrong"
    elif mutation == "id":
        payload["application_id"] = "wrong"
    elif mutation == "status":
        payload["status"] = "wrong"
    elif mutation == "scope":
        payload["application_scope"] = "ALL"
    elif mutation == "application":
        payload["application_status"] = "NOT_APPLIED"
    elif mutation == "price":
        payload["price_application"]["applied_price_kzt"] += 1
    elif mutation == "reconciliation":
        payload["reconciliation"]["coverage"]["uncovered"] = 1
    elif mutation == "technical":
        payload["technical_composition"]["status"] = "CHANGED"
    else:
        payload["safety"]["quote_generation_authorized"] = True
    digest = rewrite_predecessor(path, payload, monkeypatch)
    with pytest.raises(writer.ContractError, match=message):
        writer.load_and_validate_predecessor(path, digest)


def test_predecessor_validator_error_is_wrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, _payload = synthetic_predecessor(tmp_path, monkeypatch)

    def fail(_payload: dict[str, Any]) -> None:
        raise writer.application.ContractError("synthetic application mismatch")

    monkeypatch.setattr(writer.application, "validate_payload", fail)
    with pytest.raises(writer.ContractError, match="predecessor contract mismatch"):
        writer.load_and_validate_predecessor(path, digest)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("position", "position evidence"),
        ("membership", "position evidence|membership"),
        ("summary", "schema const|ledger summary"),
        ("grain", "schema const|price grain"),
        ("source", "actual SHA mismatch"),
        ("predecessor", "predecessor binding"),
        ("reconciliation", "reconciliation"),
        ("technical", "technical composition"),
        ("safety", "schema const|safety boundary"),
    ],
)
def test_successor_drift_fails_closed(
    mutation: str,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, _path, _digest = valid_payload(tmp_path, monkeypatch)
    if mutation == "position":
        payload["positions"][0]["approved_unit_price_kzt"] += 1
    elif mutation == "membership":
        payload["positions"][0]["invoice_position_number"] = 2
    elif mutation == "summary":
        payload["ledger_summary"]["derived_line_total_kzt"] += 1
    elif mutation == "grain":
        payload["price_grain"]["arbitrary_allocation_used"] = True
    elif mutation == "source":
        payload["source_input_bindings"][0]["actual_sha256"] = "0" * 64
    elif mutation == "predecessor":
        payload["predecessor"]["expected_sha256"] = "0" * 64
    elif mutation == "reconciliation":
        payload["reconciliation"]["coverage"]["overlap"] = 1
    elif mutation == "technical":
        payload["technical_composition"]["status"] = "CHANGED"
    else:
        payload["safety"]["client_send_authorized"] = True
    with pytest.raises(writer.ContractError, match=message):
        writer.validate_payload(payload)


def test_extra_field_bad_timestamp_and_bad_multiplicity_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, path, digest = valid_payload(tmp_path, monkeypatch)
    payload["lead_time"] = "30-40 working days"
    with pytest.raises(writer.ContractError, match="schema extra keys"):
        writer.validate_payload(payload)
    loaded = writer.load_and_validate_predecessor(path, digest)
    with pytest.raises(writer.ContractError, match="created_at_utc format"):
        writer.build_payload(loaded, "not-a-timestamp")
    payload = writer.build_payload(loaded, "2026-08-28T02:00:00Z")
    payload["positions"][0]["approved_position_total_kzt"] += 1
    monkeypatch.setattr(writer, "_positions_payload", lambda: payload["positions"])
    with pytest.raises(writer.ContractError, match="line total|multiplicity"):
        writer.validate_payload(payload)


def test_output_policy_is_outside_repo_new_directory_and_exact_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    predecessor_path, digest, _payload = synthetic_predecessor(tmp_path, monkeypatch)
    inside = PROJECT_ROOT / ".ledger-runtime-test" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="outside repository"):
        writer.publish_ledger(predecessor_path, digest, inside)
    assert not inside.parent.exists()
    existing = tmp_path / "existing" / writer.OUTPUT_FILENAME
    existing.parent.mkdir()
    with pytest.raises(writer.ContractError, match="directory already exists"):
        writer.publish_ledger(predecessor_path, digest, existing)
    wrong_name = tmp_path / "new" / "wrong.json"
    with pytest.raises(writer.ContractError, match="filename mismatch"):
        writer.publish_ledger(predecessor_path, digest, wrong_name)
    unavailable_owner = tmp_path / "missing-owner" / "new" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="owner must already exist"):
        writer.publish_ledger(predecessor_path, digest, unavailable_owner)


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
    output = tmp_path / "new-ledger" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="TOCTOU"):
        writer.publish_ledger(predecessor_path, digest, output)
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

    def fail_after_link(payload: dict[str, Any]) -> None:
        original_validate(payload)
        if link_completed:
            raise writer.ContractError("synthetic post-link failure")

    monkeypatch.setattr(writer.os, "link", observed_link)
    monkeypatch.setattr(writer, "validate_payload", fail_after_link)
    allow_synthetic_output(tmp_path, monkeypatch)
    output = tmp_path / "new-ledger" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="synthetic post-link"):
        writer.publish_ledger(predecessor_path, digest, output)
    assert link_completed is True
    assert not output.exists()
    assert not output.parent.exists()


def test_schema_source_and_safety_are_closed() -> None:
    schema = writer.load_schema()
    properties = schema["properties"]
    assert schema["additionalProperties"] is False
    assert properties["schema_version"]["const"] == writer.SCHEMA_VERSION
    assert properties["status"]["const"] == writer.STATUS
    assert properties["positions"]["minItems"] == 88
    assert properties["positions"]["maxItems"] == 88
    assert properties["safety"]["const"] == writer.SAFETY
    assert (
        writer.PUBLICATION_AUTHORIZATION != writer.application.PUBLICATION_AUTHORIZATION
    )

    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])
    assert "subprocess" not in imported
    assert "openpyxl" not in imported
    assert "run_invoice_quote" not in source
    assert "checked_clientize" not in source
    assert "30–40" not in source
