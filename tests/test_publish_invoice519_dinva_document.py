from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from openpyxl import Workbook  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]


def load_publisher() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "invoice519_document_publisher_for_tests",
        ROOT / "scripts" / "publish_invoice519_dinva_document.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def make_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    publisher = load_publisher()
    publisher.__dict__["REPO_ROOT"] = tmp_path / "repo"
    publisher.__dict__["POSITION_COUNT"] = 2
    publisher.__dict__["SECTION_COUNT"] = 2
    publisher.__dict__["APPROVED_TOTAL"] = 300
    publisher.__dict__["FROZEN_55_SUBTOTAL"] = 200
    publisher.__dict__["CHECKED_MISSING_33_SUBTOTAL"] = 100
    publisher.__dict__["YAUO_POSITION"] = 2
    publisher.__dict__["YAUO_SOURCE_CELL"] = "G19"
    publisher.__dict__["REQUIRED_LEDGER_SOURCE_ROLES"] = {"canonical_invoice_519"}
    canonical = tmp_path / "canonical.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Лист1"
    sheet["C9"] = publisher.TITLE
    sheet["C10"] = "Плательщик: Synthetic Customer"
    sheet["C13"] = "Synthetic Object"
    sheet["F15"] = publisher.APPARATUS_HEADING
    sheet["C16"] = "Секция 9"
    sheet["B17"], sheet["C17"], sheet["D17"], sheet["E17"] = 1, "Item 1", "шт.", 1
    sheet["F17"], sheet["G17"] = "QF1 apparatus", "Box 1"
    sheet["C18"] = "Секция 10"
    sheet["B19"], sheet["C19"], sheet["D19"], sheet["E19"] = 2, "Item 2", "шт.", 2
    sheet["F19"], sheet["G19"] = "QF2 apparatus", "Old YAUO enclosure"
    commercial = [
        "Счёт действителен в течении 3 банковских дней",
        "Электрооборудование обмену и возврату не подлежит",
        "Спецификация счёта после внесения предоплаты изменению не подлежит",
        "К счёту выше одного миллиона тенге прилагается договор.",
        "Оплата данного счёта подразумевает полное согласие плательщика.",
        "Предположительный срок изготовления 30-40 рабочих дней после оплаты.",
        "Точный срок изготовления уточнять после оплаты.",
        "Примечание: условия поставки EXW г. Астана",
    ]
    for row, value in enumerate(commercial, start=116):
        sheet.cell(row, 3).value = value
    sheet["C115"] = "ВСЕГО: synthetic, в том числе НДС 0%."
    sheet["C125"], sheet["F125"] = "Директор", "Никольченко И.В."
    sheet["H125"], sheet["H126"] = "Исполнитель: ", "Инженер-Электрик ПТО Марат А.К."
    workbook.save(canonical)
    canonical_sha = hashlib.sha256(canonical.read_bytes()).hexdigest()
    publisher.__dict__["CANONICAL_INVOICE_SHA256"] = canonical_sha
    positions = [
        {
            "invoice_position_number": 1,
            "quantity": 1,
            "approved_unit_price_kzt": 100,
            "approved_position_total_kzt": 100,
            "pricing_provenance": {"partition": "CHECKED_MISSING_33"},
            "technical_description_reference": {"worksheet": "Лист1", "row": 17},
        },
        {
            "invoice_position_number": 2,
            "quantity": 2,
            "approved_unit_price_kzt": 100,
            "approved_position_total_kzt": 200,
            "pricing_provenance": {"partition": "FROZEN_55"},
            "technical_description_reference": {"worksheet": "Лист1", "row": 19},
        },
    ]
    ledger_payload = {
        "schema_version": "invoice519_commercial_pricing_ledger.v0.1",
        "project_id": "2024/086",
        "invoice_number": 519,
        "ledger_id": "SYNTHETIC-LEDGER",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_status": "APPLIED",
        "price_grain": {
            "unit_prices_recalculated": False,
            "arbitrary_allocation_used": False,
        },
        "source_input_bindings": [
            {
                "role": "canonical_invoice_519",
                "path": str(canonical),
                "expected_sha256": canonical_sha,
                "actual_sha256": canonical_sha,
            }
        ],
        "positions": positions,
        "ledger_summary": {
            "position_count": 2,
            "approved_total_kzt": 300,
            "derived_line_total_kzt": 300,
            "frozen_55_subtotal_kzt": 200,
            "checked_missing_33_subtotal_kzt": 100,
            "price_recalculation_used": False,
        },
        "safety": {
            "quote_generation_authorized": False,
            "invoice_generation_authorized": False,
            "client_send_authorized": False,
        },
    }
    ledger = tmp_path / "ledger.json"
    ledger_sha = write_json(ledger, ledger_payload)
    publisher.__dict__["LEDGER_SHA256"] = ledger_sha
    yauo_payload = {
        "schema_version": "invoice519_yauo_enclosure_human_decision.v0.1",
        "decision_id": "SYNTHETIC-YAUO-DECISION",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "approval_scope": "ENCLOSURE_DIMENSIONS_ONLY",
        "quote_application_status": "NOT_APPLIED",
        "source_binding": {
            "path": str(canonical),
            "expected_sha256": canonical_sha,
            "actual_sha256": canonical_sha,
            "worksheet": "Лист1",
            "cell": "G19",
            "canonical_cell_value": "Old YAUO enclosure",
        },
        "technical_decision": {
            "invoice_position_number": 2,
            "approved_value": publisher.YAUO_APPROVED_DIMENSIONS,
            "change_scope": "POSITION_2_ENCLOSURE_ONLY",
        },
    }
    yauo = tmp_path / "yauo.json"
    yauo_sha = write_json(yauo, yauo_payload)
    publisher.__dict__["YAUO_DECISION_SHA256"] = yauo_sha
    monkeypatch.setattr(publisher, "utc_now", lambda: "2026-09-03T00:00:00Z")
    return {
        "publisher": publisher,
        "ledger": publisher.BoundInput(ledger, ledger_sha),
        "yauo": publisher.BoundInput(yauo, yauo_sha),
        "canonical": publisher.BoundInput(canonical, canonical_sha),
        "ledger_payload": ledger_payload,
        "yauo_payload": yauo_payload,
        "draft_output": tmp_path / "draft-case" / publisher.DRAFT_OUTPUT_FILENAME,
        "output": tmp_path / "case" / publisher.OUTPUT_FILENAME,
    }


def prepare_draft(case: dict[str, Any]) -> Any:
    publisher = case["publisher"]
    return publisher.publish_draft_document(
        case["ledger"],
        case["yauo"],
        case["canonical"],
        case["draft_output"],
    )


def approval_subject(case: dict[str, Any]) -> tuple[Any, Any]:
    publisher = case["publisher"]
    if not case["draft_output"].exists():
        prepare_draft(case)
    raw = case["draft_output"].read_bytes()
    source = publisher.BoundInput(case["draft_output"], publisher.sha256_bytes(raw))
    return source, publisher.load_draft_document(source)


def publish(case: dict[str, Any], authorization: str | None = None) -> Any:
    publisher = case["publisher"]
    source, loaded = approval_subject(case)
    return publisher.publish_document(
        source,
        case["output"],
        (
            authorization
            if authorization is not None
            else publisher.authorization_for(loaded)
        ),
    )


def test_positive_immutable_source_bound_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = make_case(tmp_path, monkeypatch)
    result = publish(case)
    payload = json.loads(result.path.read_text(encoding="utf-8"))
    draft = json.loads(case["draft_output"].read_text(encoding="utf-8"))
    assert [section["label"] for section in payload["sections"]] == [
        "Секция 9",
        "Секция 10",
    ]
    assert payload["approved_grand_total_kzt"] == 300
    assert payload["basis"] == "2024/086"
    assert payload["terms"]["manufacturing_lead_time"] == "30–40 рабочих дней"
    assert payload["terms"]["payment"] is None
    commercial_lines = payload["terms"]["commercial_lines"]
    assert [line["source_order"] for line in commercial_lines] == list(range(1, 9))
    assert [line["text"] for line in commercial_lines] == [
        "Счёт действителен в течении 3 банковских дней",
        "Электрооборудование обмену и возврату не подлежит",
        "Спецификация счёта после внесения предоплаты изменению не подлежит",
        "К счёту выше одного миллиона тенге прилагается договор.",
        "Оплата данного счёта подразумевает полное согласие плательщика.",
        "Предположительный срок изготовления 30-40 рабочих дней после оплаты.",
        "Точный срок изготовления уточнять после оплаты.",
        "Примечание: условия поставки EXW г. Астана",
    ]
    assert {line["source_sha256"] for line in commercial_lines} == {
        case["canonical"].expected_sha256
    }
    assert [line["source_locator"] for line in commercial_lines] == [
        f"Лист1!C{row}" for row in range(116, 124)
    ]
    assert payload["terms"]["manufacturing_lead_time_provenance"] == {
        "source_order": 6,
        "source_text": commercial_lines[5]["text"],
        "normalized_text": "30–40 рабочих дней",
        "source_sha256": case["canonical"].expected_sha256,
        "source_locator": "Лист1!C121",
        "normalization_rule": case["publisher"].LEAD_TIME_NORMALIZATION_RULE,
        "approval_reference": case["publisher"].LEAD_TIME_APPROVAL_REFERENCE,
    }
    assert (
        payload["document_fingerprint"]
        == payload["approval_provenance"]["approved_document_fingerprint"]
    )
    assert payload["items"][1]["enclosure"] == case["publisher"].YAUO_APPROVED_ENCLOSURE
    assert (
        payload["items"][1]["approval_reference"]["enclosure"]
        == "SYNTHETIC-YAUO-DECISION"
    )
    assert payload["approval_provenance"]["client_send_authorized"] is False
    assert {
        key: value for key, value in payload.items() if key != "approval_provenance"
    } == {key: value for key, value in draft.items() if key != "approval_provenance"}
    allowed_changes = {
        "status",
        "authority",
        "approval_id",
        "approved_at",
        "approved_document_fingerprint",
        "rendering_authorized",
    }
    assert {
        key: value
        for key, value in payload["approval_provenance"].items()
        if key not in allowed_changes
    } == {
        key: value
        for key, value in draft["approval_provenance"].items()
        if key not in allowed_changes
    }
    assert set(result.path.parent.iterdir()) == {result.path}


def test_draft_publication_is_source_bound_and_not_render_authorized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = make_case(tmp_path, monkeypatch)
    publisher = case["publisher"]
    output = tmp_path / "draft-case" / publisher.DRAFT_OUTPUT_FILENAME
    result = publisher.publish_draft_document(
        case["ledger"], case["yauo"], case["canonical"], output
    )
    payload = json.loads(result.path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "dinva_quote_invoice_document.v0.2"
    assert payload["terms"]["payment"] is None
    assert payload["approval_provenance"]["status"] == "DRAFT_UNAPPROVED"
    assert payload["approval_provenance"]["approved_document_fingerprint"] is None
    assert payload["approval_provenance"]["rendering_authorized"] is False
    assert payload["approval_provenance"]["client_send_authorized"] is False
    assert len(payload["terms"]["commercial_lines"]) == 8
    assert set(result.path.parent.iterdir()) == {result.path}


@pytest.mark.parametrize("wrong_basis", [None, "WRONG"])
def test_built_document_rejects_null_or_wrong_invoice519_basis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wrong_basis: object,
) -> None:
    case = make_case(tmp_path, monkeypatch)
    publisher = case["publisher"]
    sources = publisher.load_sources(case["ledger"], case["yauo"], case["canonical"])
    document = publisher.build_draft_document(sources)
    document["basis"] = wrong_basis
    governed = {
        key: value
        for key, value in document.items()
        if key not in {"approval_provenance", "document_fingerprint"}
    }
    fingerprint = publisher.sha256_bytes(publisher.canonical_json(governed))
    document["document_fingerprint"] = fingerprint
    document["approval_provenance"]["approved_document_fingerprint"] = None
    with pytest.raises(
        publisher.DocumentPublicationError, match="built document identity mismatch"
    ):
        publisher.validate_built_document(document, expected_status="DRAFT_UNAPPROVED")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda case: case.update(
                ledger=case["publisher"].BoundInput(case["ledger"].path, "0" * 64)
            ),
            "approved artifact SHA",
        ),
        (
            lambda case: case["ledger_payload"]["ledger_summary"].update(
                approved_total_kzt=301
            ),
            "approved total mismatch",
        ),
        (
            lambda case: case["yauo_payload"]["technical_decision"].update(
                approved_value="WRONG"
            ),
            "approved dimensions mismatch",
        ),
        (
            lambda case: case["ledger_payload"].update(project_id=None),
            "ledger identity mismatch",
        ),
        (
            lambda case: case["ledger_payload"].update(project_id="WRONG"),
            "ledger identity mismatch",
        ),
    ],
)
def test_fail_closed_source_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: Any,
    message: str,
) -> None:
    case = make_case(tmp_path, monkeypatch)
    mutation(case)
    if case["ledger_payload"] != json.loads(
        case["ledger"].path.read_text(encoding="utf-8")
    ):
        ledger_sha = write_json(case["ledger"].path, case["ledger_payload"])
        case["publisher"].__dict__["LEDGER_SHA256"] = ledger_sha
        case["ledger"] = case["publisher"].BoundInput(case["ledger"].path, ledger_sha)
    if case["yauo_payload"] != json.loads(
        case["yauo"].path.read_text(encoding="utf-8")
    ):
        yauo_sha = write_json(case["yauo"].path, case["yauo_payload"])
        case["publisher"].__dict__["YAUO_DECISION_SHA256"] = yauo_sha
        case["yauo"] = case["publisher"].BoundInput(case["yauo"].path, yauo_sha)
    with pytest.raises(case["publisher"].DocumentPublicationError, match=message):
        prepare_draft(case)
    assert not case["draft_output"].exists()


@pytest.mark.parametrize(
    ("token_kind", "message"),
    [
        ("wrong-draft-sha", "DRAFT document SHA-256 mismatch"),
        ("wrong-fingerprint", "content-bound document approval"),
        ("old-static", "content-bound document approval"),
    ],
)
def test_content_bound_authorization_rejects_wrong_subject_or_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    token_kind: str,
    message: str,
) -> None:
    case = make_case(tmp_path, monkeypatch)
    prepare_draft(case)
    publisher = case["publisher"]
    source, loaded = approval_subject(case)
    authorization = publisher.authorization_for(loaded)
    if token_kind == "wrong-draft-sha":
        source = publisher.BoundInput(source.path, "0" * 64)
    elif token_kind == "wrong-fingerprint":
        authorization = (
            f"{publisher.PUBLICATION_AUTHORIZATION_PREFIX}|"
            f"DRAFT_SHA256={loaded.sha256}|DOCUMENT_FINGERPRINT={'0' * 64}"
        )
    else:
        authorization = publisher.PUBLICATION_AUTHORIZATION_PREFIX
    with pytest.raises(publisher.DocumentPublicationError, match=message):
        publisher.publish_document(source, case["output"], authorization)
    assert not case["output"].exists()


def test_mutated_draft_after_token_formation_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = make_case(tmp_path, monkeypatch)
    source, loaded = approval_subject(case)
    authorization = case["publisher"].authorization_for(loaded)
    payload = json.loads(source.path.read_text(encoding="utf-8"))
    payload["payer"] = "MUTATED AFTER REVIEW"
    write_json(source.path, payload)
    with pytest.raises(
        case["publisher"].DocumentPublicationError,
        match="DRAFT document SHA-256 mismatch",
    ):
        case["publisher"].publish_document(source, case["output"], authorization)
    assert not case["output"].exists()


def test_no_overwrite_and_approval_toctou_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = make_case(tmp_path, monkeypatch)
    case["output"].parent.mkdir()
    case["output"].write_text("occupied", encoding="utf-8")
    with pytest.raises(
        case["publisher"].DocumentPublicationError, match="already exists"
    ):
        publish(case)
    case = make_case(tmp_path / "second", monkeypatch)
    publish(case)
    with pytest.raises(
        case["publisher"].DocumentPublicationError, match="already exists"
    ):
        publish(case)

    case = make_case(tmp_path / "third", monkeypatch)
    publisher = case["publisher"]
    source, loaded = approval_subject(case)
    original = publisher.recheck_draft_document

    def mutate(draft: Any) -> None:
        draft.bound_sources[1][1].path.write_text("{}", encoding="utf-8")
        original(draft)

    monkeypatch.setattr(publisher, "recheck_draft_document", mutate)
    with pytest.raises(publisher.DocumentPublicationError, match="TOCTOU"):
        publisher.publish_document(
            source, case["output"], publisher.authorization_for(loaded)
        )
    assert not case["output"].exists()
    assert not case["output"].parent.exists()


def test_missing_authoritative_mapping_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = make_case(tmp_path, monkeypatch)
    case["ledger_payload"]["positions"][0]["technical_description_reference"][
        "row"
    ] = 18
    ledger_sha = write_json(case["ledger"].path, case["ledger_payload"])
    case["publisher"].__dict__["LEDGER_SHA256"] = ledger_sha
    case["ledger"] = case["publisher"].BoundInput(case["ledger"].path, ledger_sha)
    with pytest.raises(
        case["publisher"].DocumentPublicationError, match="quantity mismatch"
    ):
        publish(case)
