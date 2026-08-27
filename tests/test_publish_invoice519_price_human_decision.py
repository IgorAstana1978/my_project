from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import py_compile
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "publish_invoice519_price_human_decision.py"


def load_writer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "publish_invoice519_price_human_decision_for_test", SCRIPT
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
        "schema_version": ("technical_invoice519_pricing_profile_human_decisions.v0.1"),
        "status": "IGOR_INVOICE519_PRICING_PROFILE_APPROVED_NOT_APPLIED",
        "application_status": "NOT_APPLIED",
        "positions": [
            {"invoice_position_number": position}
            for position in writer.FROZEN_55_POSITIONS
        ],
    }


def synthetic_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Path], dict[str, str]]:
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
    for original in writer.INPUT_SPECS:
        suffix = ".json" if original.media_type == writer.JSON_MEDIA_TYPE else ".xlsx"
        path = tmp_path / f"{original.role}{suffix}"
        raw = values[original.role]
        path.write_bytes(raw)
        paths[original.role] = path
        specs.append(
            writer.InputSpec(
                original.role,
                str(path.resolve()),
                sha256(raw),
                original.media_type,
            )
        )
    monkeypatch.setattr(writer, "INPUT_SPECS", tuple(specs))
    return paths, {spec.role: spec.sha256 for spec in specs}


def replace_spec_sha(role: str, raw: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    specs = tuple(
        writer.InputSpec(
            spec.role,
            spec.path,
            sha256(raw) if spec.role == role else spec.sha256,
            spec.media_type,
        )
        for spec in writer.INPUT_SPECS
    )
    monkeypatch.setattr(writer, "INPUT_SPECS", specs)


def cli_arguments(
    paths: dict[str, Path], shas: dict[str, str], output: Path, authorization: str
) -> list[str]:
    result: list[str] = []
    for spec in writer.INPUT_SPECS:
        option = spec.role.replace("_", "-")
        result.extend([f"--{option}", str(paths[spec.role])])
        result.extend([f"--{option}-sha256", shas[spec.role]])
    result.extend(["--output", str(output), "--authorization", authorization])
    return result


def valid_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], dict[str, Path], dict[str, str]]:
    paths, shas = synthetic_case(tmp_path, monkeypatch)
    loaded = writer.load_and_validate_inputs(paths, shas)
    payload = writer.build_payload(loaded, "2026-08-27T00:00:00Z")
    return payload, paths, shas


def test_writer_and_test_py_compile(tmp_path: Path) -> None:
    py_compile.compile(str(SCRIPT), cfile=str(tmp_path / "writer.pyc"), doraise=True)
    py_compile.compile(
        str(Path(__file__)), cfile=str(tmp_path / "test.pyc"), doraise=True
    )


def test_positive_payload_and_immutable_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, paths, shas = valid_payload(tmp_path, monkeypatch)
    assert payload["status"] == writer.STATUS
    assert payload["price_approval"] == {
        "approved_price_kzt": 19_499_186,
        "currency": "KZT",
        "approval_scope": "PRICE_ONLY",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_status": "NOT_APPLIED",
    }
    output = tmp_path / "new-decision" / writer.OUTPUT_FILENAME
    result = writer.publish_decision(paths, shas, output)
    assert output.is_file()
    assert result.encoded == output.read_bytes()
    assert result.sha256 == sha256(output.read_bytes())
    assert result.size == len(output.read_bytes())
    assert list(output.parent.iterdir()) == [output]


def test_authorization_fails_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas = synthetic_case(tmp_path, monkeypatch)
    output = tmp_path / "new-decision" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="publication authorization"):
        writer.main(cli_arguments(paths, shas, output, "WRONG"))
    assert not output.parent.exists()


def test_wrong_input_path_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas = synthetic_case(tmp_path, monkeypatch)
    wrong = tmp_path / "wrong.json"
    wrong.write_bytes(paths["completed_technical_input"].read_bytes())
    paths["completed_technical_input"] = wrong
    with pytest.raises(writer.ContractError, match="input path mismatch"):
        writer.load_and_validate_inputs(paths, shas)


@pytest.mark.parametrize("bad_sha", ["0" * 64, "A" * 64, "x"])
def test_wrong_or_malformed_sha_fails_closed(
    bad_sha: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas = synthetic_case(tmp_path, monkeypatch)
    shas["main_price_workbook"] = bad_sha
    with pytest.raises(writer.ContractError, match="SHA"):
        writer.load_and_validate_inputs(paths, shas)


def test_duplicate_json_keys_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas = synthetic_case(tmp_path, monkeypatch)
    raw = b'{"schema_version":"a","schema_version":"b"}'
    paths["completed_technical_input"].write_bytes(raw)
    replace_spec_sha("completed_technical_input", raw, monkeypatch)
    shas["completed_technical_input"] = sha256(raw)
    with pytest.raises(writer.ContractError, match="duplicate JSON key"):
        writer.load_and_validate_inputs(paths, shas)


def test_profile_membership_drift_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas = synthetic_case(tmp_path, monkeypatch)
    profile = pricing_profile()
    cast(list[Any], profile["positions"]).pop()
    raw = encoded(profile)
    paths["pricing_profile"].write_bytes(raw)
    replace_spec_sha("pricing_profile", raw, monkeypatch)
    shas["pricing_profile"] = sha256(raw)
    with pytest.raises(writer.ContractError, match="frozen 55 membership"):
        writer.load_and_validate_inputs(paths, shas)


def test_exact_membership_partition_and_reconciliation() -> None:
    reconciliation = writer._reconciliation_payload()
    writer.validate_reconciliation(reconciliation)
    frozen = set(writer.FROZEN_55_POSITIONS)
    missing = set(writer.MISSING_33_POSITIONS)
    assert len(frozen) == 55
    assert len(missing) == 33
    assert frozen.isdisjoint(missing)
    assert frozen | missing == set(range(1, 89))
    assert sum(item[2] for item in writer.FAMILY_SUBTOTALS) == 7_535_394
    assert 11_963_792 + 7_535_394 == 19_499_186


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("overlap", "membership|overlap"),
        ("uncovered", "membership|union"),
        ("family_overlap", "family overlap"),
        ("family_total", "family subtotal reconciliation"),
        ("combined_total", "combined total mismatch"),
        ("coverage", "coverage mismatch"),
    ],
)
def test_reconciliation_drift_fails_closed(mutation: str, message: str) -> None:
    value = writer._reconciliation_payload()
    missing = value["checked_missing_33"]
    if mutation == "overlap":
        missing["invoice_position_numbers"][0] = 6
    elif mutation == "uncovered":
        missing["invoice_position_numbers"][0] = 89
    elif mutation == "family_overlap":
        missing["family_subtotals"][1]["positions"][0] = 1
    elif mutation == "family_total":
        missing["family_subtotals"][0]["subtotal_kzt"] += 1
    elif mutation == "combined_total":
        value["combined_total_kzt"] += 1
    else:
        value["coverage"]["uncovered"] = 1
    with pytest.raises(writer.ContractError, match=message):
        writer.validate_reconciliation(value)


@pytest.mark.parametrize(
    "field_name",
    [
        field_name
        for field_name, field_value in writer.SAFETY.items()
        if not field_value
    ],
)
def test_every_closed_safety_flag_fails_if_enabled(
    field_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, _paths, _shas = valid_payload(tmp_path, monkeypatch)
    payload["safety"][field_name] = True
    with pytest.raises(writer.ContractError, match="schema const|safety boundary"):
        writer.validate_payload(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("status", "APPLIED"),
        ("authority", "NOT_IGOR"),
        ("approval_scope", "QUOTE"),
        ("application_status", "APPLIED"),
    ],
)
def test_root_contract_drift_fails_schema(
    field_name: str,
    value: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, _paths, _shas = valid_payload(tmp_path, monkeypatch)
    payload[field_name] = value
    with pytest.raises(writer.ContractError, match="schema const"):
        writer.validate_payload(payload)


def test_extra_field_fails_closed_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, _paths, _shas = valid_payload(tmp_path, monkeypatch)
    payload["quote_authorized"] = True
    with pytest.raises(writer.ContractError, match="schema extra keys"):
        writer.validate_payload(payload)


def test_existing_output_directory_is_no_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas = synthetic_case(tmp_path, monkeypatch)
    output = tmp_path / "existing" / writer.OUTPUT_FILENAME
    output.parent.mkdir()
    with pytest.raises(writer.ContractError, match="output directory already exists"):
        writer.publish_decision(paths, shas, output)
    assert list(output.parent.iterdir()) == []


def test_toctou_change_rolls_back_staging_and_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas = synthetic_case(tmp_path, monkeypatch)
    target = paths["main_price_workbook"]
    original_read_bytes = Path.read_bytes
    target_reads = 0

    def changed_on_reread(path: Path) -> bytes:
        nonlocal target_reads
        raw = original_read_bytes(path)
        if path == target:
            target_reads += 1
            if target_reads == 2:
                return raw + b"changed"
        return raw

    monkeypatch.setattr(Path, "read_bytes", changed_on_reread)
    output = tmp_path / "new-decision" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="TOCTOU"):
        writer.publish_decision(paths, shas, output)
    assert not output.exists()
    assert not output.parent.exists()


def test_post_link_validation_failure_rolls_back_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas = synthetic_case(tmp_path, monkeypatch)
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
    output = tmp_path / "new-decision" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="synthetic post-link"):
        writer.publish_decision(paths, shas, output)
    assert link_completed is True
    assert not output.exists()
    assert not output.parent.exists()


def test_schema_is_closed_and_matches_writer_contract() -> None:
    schema = writer.load_schema()
    assert schema["additionalProperties"] is False
    properties = schema["properties"]
    assert properties["schema_version"]["const"] == writer.SCHEMA_VERSION
    assert properties["status"]["const"] == writer.STATUS
    assert properties["approval_scope"]["const"] == "PRICE_ONLY"
    assert properties["application_status"]["const"] == "NOT_APPLIED"
    assert properties["reconciliation"]["const"] == writer._reconciliation_payload()
    assert properties["safety"]["const"] == writer.SAFETY


def test_publisher_has_no_application_or_downstream_imports() -> None:
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
        "json",
        "os",
        "re",
        "tempfile",
        "collections",
        "dataclasses",
        "datetime",
        "pathlib",
        "typing",
    }
    assert "def apply_" not in source
    assert "subprocess" not in imported
