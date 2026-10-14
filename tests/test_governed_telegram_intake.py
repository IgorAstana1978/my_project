"""Synthetic offline Telegram provenance, no-overwrite and review boundaries."""

import copy
import json
import subprocess
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import governed_telegram_intake as intake  # type: ignore[import-not-found]
import pytest
from test_extract_mixed_source_composition import (
    standard_row,
    text_page,
    write_spec_workbook,
    write_text_pdf,
)


def event(kind: str = "text", body: bytes | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {
        "message_id": 11,
        "date": 1780000000,
        "chat": {"id": -1001, "type": "supergroup"},
    }
    if kind == "text":
        message["text"] = "  Запрос\nVRU-1 — проверить состав.\n"
    else:
        message["caption"] = "  Исходная подпись\nБез решения о составе.  "
        message["document"] = {
            "file_id": "synthetic-download",
            "file_unique_id": "synthetic-stable",
            "file_name": f"original.{kind}",
            "file_size": len(body or b""),
        }
    return {"update_id": 99, "message": message}


@pytest.fixture
def outputs(tmp_path: Path) -> tuple[Path, Path]:
    receipt, case = tmp_path / "receipts", tmp_path / "cases"
    receipt.mkdir()
    case.mkdir()
    return receipt, case


def receive(
    outputs: tuple[Path, Path],
    data: dict[str, Any],
    body: bytes | None = None,
    **kwargs: Any,
) -> intake.TelegramResult:
    return intake.receive_event(
        raw_update=intake.encode(data),
        policy=intake.TelegramPolicy(777, frozenset({-1001})),
        receipt_root=outputs[0],
        case_root=outputs[1],
        document_bytes=body,
        expected_document_sha256=intake.sha(body) if body is not None else None,
        **kwargs,
    )


def snapshot(path: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("kind", ["text", "pdf", "xlsx"])
def test_real_existing_extractor_handoff_and_duplicate(
    outputs: tuple[Path, Path], tmp_path: Path, kind: str
) -> None:
    body = None
    if kind == "pdf":
        body = write_text_pdf(tmp_path / "fixture.pdf", [text_page()]).read_bytes()
    elif kind == "xlsx":
        body = write_spec_workbook(
            tmp_path / "fixture.xlsx", {"Spec": [standard_row()]}
        ).read_bytes()
    data = event(kind, body)
    result = receive(outputs, data, body)
    assert result.status == "REVIEW_REQUIRED", result.blocker
    assert result.case_id and result.package
    package = json.loads(result.package.read_bytes())
    receipt_dir = outputs[0] / result.case_id
    case_dir = outputs[1] / result.case_id
    receipt = json.loads((receipt_dir / "receipt.json").read_bytes())
    assert receipt["identity"] == {
        "bot_id": 777,
        "update_id": 99,
        "chat_id": -1001,
        "message_id": 11,
    }
    assert package["receipt_sha256"] == intake.sha(
        (receipt_dir / "receipt.json").read_bytes()
    )
    assert package["stop_before"] == "HUMAN_APPROVAL_1"
    field = "text" if kind == "text" else "caption"
    assert (receipt_dir / f"{field}.txt").read_bytes() == data["message"][field].encode(
        "utf-8"
    )
    assert (receipt_dir / "update.json").read_bytes() == intake.encode(data)
    if body is not None:
        assert (receipt_dir / f"source.{kind}").read_bytes() == body
        assert receipt["document"]["sha256"] == intake.sha(body)
    draft = json.loads((case_dir / "preliminary-composition-draft.json").read_bytes())
    assert draft["safety"]["confirmed_by_igor"] is False
    assert all(
        value is False for name, value in draft["safety"].items() if name != "status"
    )
    assert bool(draft["items"]) is (kind != "text")
    manifest = json.loads((case_dir / "source-bundle-manifest.txt").read_bytes())
    assert len(manifest["sources"]) == 1
    if kind == "text":
        assert draft["source"]["source_type"] == "text_request"
        assert draft["extraction_summary"]["ready_for_preliminary_workflow"] is False
        assert manifest["sources"][0]["sha256"] == intake.sha(
            data["message"]["text"].encode("utf-8")
        )
    else:
        assert manifest["sources"][0]["source_type"] == (
            "pdf" if kind == "pdf" else "workbook"
        )
    assert (case_dir / "igor-review-card.md").is_file()
    assert not (case_dir / "confirmed").exists()
    before = snapshot(outputs[0]), snapshot(outputs[1])
    retry = receive(outputs, data, body)
    assert retry.status == "REVIEW_REQUIRED" and retry.duplicate
    assert retry.case_id == result.case_id
    assert before == (snapshot(outputs[0]), snapshot(outputs[1]))
    assert len(list(outputs[1].iterdir())) == 1


@pytest.mark.parametrize(
    "change",
    [
        "wrong_chat",
        "identity_bool",
        "missing_id",
        "negative_update",
        "bad_date",
        "unsupported_update",
        "photo",
        "empty_text",
        "text_object",
        "caption_only",
        "no_input",
        "chat_object",
        "text_caption",
        "large_id",
    ],
)
def test_invalid_events_hold_without_writes(
    outputs: tuple[Path, Path], change: str
) -> None:
    data = event()
    message = data["message"]
    if change == "wrong_chat":
        message["chat"]["id"] = -1002
    elif change == "identity_bool":
        data["update_id"] = True
    elif change == "missing_id":
        message.pop("message_id")
    elif change == "negative_update":
        data["update_id"] = -1
    elif change == "bad_date":
        message["date"] = None
    elif change == "unsupported_update":
        data["edited_message"] = data.pop("message")
    elif change == "photo":
        message["photo"] = []
    elif change == "empty_text":
        message["text"] = " "
    elif change == "text_object":
        message["text"] = {}
    elif change == "caption_only":
        message["caption"] = message.pop("text")
    elif change == "no_input":
        message.pop("text")
    elif change == "chat_object":
        message["chat"] = []
    elif change == "text_caption":
        message["caption"] = "caption"
    elif change == "large_id":
        data["update_id"] = 2**53
    result = receive(outputs, data)
    assert result.status == "HOLD"
    assert not list(outputs[0].iterdir()) and not list(outputs[1].iterdir())


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not-json",
        b"\xff",
        b"{}",
        b'{"update_id":1,"update_id":2}',
        b'{"message":[],"update_id":0}',
    ],
)
def test_malformed_raw(outputs: tuple[Path, Path], raw: bytes) -> None:
    result = intake.receive_event(
        raw_update=raw,
        policy=intake.TelegramPolicy(777, frozenset({-1001})),
        receipt_root=outputs[0],
        case_root=outputs[1],
    )
    assert result.status == "HOLD"


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "sha",
        "size",
        "suffix",
        "mime",
        "filename",
        "file_id",
        "signature",
        "unknown",
        "text",
    ],
)
def test_bad_documents(outputs: tuple[Path, Path], change: str) -> None:
    body: bytes | None = b"%PDF-synthetic-not-parsed"
    data = event("pdf", body)
    doc = data["message"]["document"]
    if change == "missing":
        body = None
    elif change == "sha":
        result = intake.receive_event(
            raw_update=intake.encode(data),
            policy=intake.TelegramPolicy(777, frozenset({-1001})),
            receipt_root=outputs[0],
            case_root=outputs[1],
            document_bytes=body,
            expected_document_sha256="0" * 64,
        )
        assert result.status == "HOLD"
        return
    elif change == "size":
        doc["file_size"] = 1
    elif change == "suffix":
        doc["file_name"] = "input.xls"
    elif change == "mime":
        doc["mime_type"] = "image/jpeg"
    elif change == "filename":
        doc["file_name"] = "../input.pdf"
    elif change == "file_id":
        doc["file_id"] = None
    elif change == "signature":
        body = b"fake"
        doc.pop("file_size")
    elif change == "unknown":
        doc["token"] = "forbidden-field"
    elif change == "text":
        data["message"]["text"] = "ambiguous"
    assert receive(outputs, data, body).status == "HOLD"
    assert not list(outputs[0].iterdir())


def test_changed_redelivery_and_review_hold(outputs: tuple[Path, Path]) -> None:
    data = event()
    result = receive(outputs, data)
    assert result.case_id and result.package
    before = snapshot(outputs[0]), snapshot(outputs[1])
    changed = copy.deepcopy(data)
    changed["message"]["text"] += " changed"
    assert receive(outputs, changed).status == "HOLD"
    changed = copy.deepcopy(data)
    changed["message"]["message_id"] += 1
    assert receive(outputs, changed).status == "HOLD"
    assert before == (snapshot(outputs[0]), snapshot(outputs[1]))
    review = outputs[1] / result.case_id / "igor-review-card.md"
    review.write_bytes(b"changed")
    assert receive(outputs, data).status == "HOLD"


@pytest.mark.parametrize(
    "target", ["text.txt", "receipt.json", "operator-package.json", "extra"]
)
def test_receipt_tamper_hold(outputs: tuple[Path, Path], target: str) -> None:
    data = event()
    result = receive(outputs, data)
    assert result.case_id
    path = outputs[0] / result.case_id / target
    if target == "operator-package.json":
        package = json.loads(path.read_bytes())
        package["composition_confirmed"] = True
        path.write_bytes(intake.encode(package))
    else:
        path.write_bytes(b"changed")
    before = snapshot(outputs[0]), snapshot(outputs[1])
    assert receive(outputs, data).status == "HOLD"
    assert before == (snapshot(outputs[0]), snapshot(outputs[1]))


def test_existing_case_and_interrupted_receipt_preserved(
    outputs: tuple[Path, Path],
) -> None:
    data = event()
    case_id, _, _ = intake.parse_event(
        intake.encode(data), None, None, intake.TelegramPolicy(777, frozenset({-1001}))
    )
    case = outputs[1] / case_id
    case.mkdir()
    marker = case / "existing.txt"
    marker.write_bytes(b"preserved")
    assert receive(outputs, data).status == "HOLD"
    assert marker.read_bytes() == b"preserved"
    assert not list(outputs[0].iterdir())
    folder = outputs[0] / case_id
    folder.mkdir()
    assert receive(outputs, data).status == "HOLD"
    assert not list(folder.iterdir())


def test_concurrent_delivery_single_case(outputs: tuple[Path, Path]) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: receive(outputs, event()), range(2)))
    assert any(result.status == "REVIEW_REQUIRED" for result in results)
    assert len(list(outputs[1].iterdir())) == 1
    assert receive(outputs, event()).duplicate


def test_external_configuration_and_secret_rejection(
    outputs: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    policy = intake.TelegramPolicy.from_environment(
        {"WU10_TELEGRAM_BOT_ID": "777", "WU10_TELEGRAM_ALLOWED_CHATS": "-1001,123"}
    )
    assert policy.allowed_chat_ids == frozenset({-1001, 123})
    for env in ({}, {"WU10_TELEGRAM_BOT_ID": "777", "WU10_TELEGRAM_ALLOWED_CHATS": ""}):
        with pytest.raises(intake.TelegramHold):
            intake.TelegramPolicy.from_environment(env)
    secret_like = "123456:" + "x" * 25
    data = event()
    data["message"]["text"] = secret_like
    result = receive(outputs, data)
    assert result.status == "HOLD"
    assert secret_like not in repr(result)
    assert capsys.readouterr() == ("", "")
    assert not list(outputs[0].iterdir())


def test_extraction_fail_remains_hold(
    outputs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        intake, "run_case_extraction", lambda **kwargs: SimpleNamespace(status="FAIL")
    )
    body = b"%PDF-corrupt"
    result = receive(outputs, event("pdf", body), body)
    assert result.status == "HOLD"
    assert receive(outputs, event("pdf", body), body).status == "HOLD"
    assert not list(outputs[1].iterdir())


def test_unsafe_or_overlapping_roots(outputs: tuple[Path, Path]) -> None:
    policy = intake.TelegramPolicy(777, frozenset({-1001}))
    for receipt, case in (
        (outputs[0], outputs[0]),
        (outputs[0] / "missing", outputs[1]),
        (intake.PROJECT_ROOT, outputs[1]),
    ):
        result = intake.receive_event(
            raw_update=intake.encode(event()),
            policy=policy,
            receipt_root=receipt,
            case_root=case,
        )
        assert result.status == "HOLD"


def test_unsafe_path_detection(
    outputs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(intake, "_unsafe_reparse", lambda path: path == outputs[0])
    assert receive(outputs, event()).status == "HOLD"


def test_invalid_policy() -> None:
    for policy in (
        intake.TelegramPolicy(0, frozenset({1})),
        intake.TelegramPolicy(1, frozenset()),
        intake.TelegramPolicy(1, frozenset({True})),
    ):
        with pytest.raises(intake.TelegramHold):
            policy.validate()


def test_policy_owner_keeps_exact_baseline_bytes() -> None:
    root = Path(__file__).resolve().parents[1]
    baseline = subprocess.check_output(
        [
            "git",
            "show",
            "HEAD:scripts/project_spec_extraction.py",
        ],
        cwd=root,
    )
    assert (root / "scripts" / "project_spec_extraction.py").read_bytes() == baseline


def test_secret_configuration_traceback_is_safe() -> None:
    marker = "123456:" + "x" * 25
    with pytest.raises(intake.TelegramHold) as caught:
        intake.TelegramPolicy.from_environment(
            {"WU10_TELEGRAM_BOT_ID": marker, "WU10_TELEGRAM_ALLOWED_CHATS": "1"}
        )
    assert marker not in "".join(traceback.format_exception(caught.value))


def test_deep_json_holds(outputs: tuple[Path, Path]) -> None:
    result = intake.receive_event(
        raw_update=b"[" * 2000 + b"]" * 2000,
        policy=intake.TelegramPolicy(777, frozenset({-1001})),
        receipt_root=outputs[0],
        case_root=outputs[1],
    )
    assert result.status == "HOLD"


def test_malformed_package_hash_map_holds(outputs: tuple[Path, Path]) -> None:
    result = receive(outputs, event())
    assert result.package
    package = json.loads(result.package.read_bytes())
    package["review_files"] = sorted(intake.EXPECTED_FILES)
    result.package.write_bytes(intake.encode(package))
    assert receive(outputs, event()).status == "HOLD"


@pytest.mark.parametrize("kind", ["pdf", "xlsx"])
def test_document_without_caption(
    outputs: tuple[Path, Path], tmp_path: Path, kind: str
) -> None:
    body = (
        write_text_pdf(tmp_path / "fixture.pdf", [text_page()])
        if kind == "pdf"
        else write_spec_workbook(tmp_path / "fixture.xlsx", {"Spec": [standard_row()]})
    ).read_bytes()
    data = event(kind, body)
    data["message"].pop("caption")
    result = receive(outputs, data, body)
    assert result.status == "REVIEW_REQUIRED", result.blocker
    assert receive(outputs, data, body).duplicate


def test_changed_document_delivery_holds(
    outputs: tuple[Path, Path], tmp_path: Path
) -> None:
    body = write_text_pdf(tmp_path / "fixture.pdf", [text_page()]).read_bytes()
    data = event("pdf", body)
    assert receive(outputs, data, body).status == "REVIEW_REQUIRED"
    changed = body + b"\nchanged"
    before = snapshot(outputs[0]), snapshot(outputs[1])
    assert receive(outputs, event("pdf", changed), changed).status == "HOLD"
    assert before == (snapshot(outputs[0]), snapshot(outputs[1]))


def test_confirmation_directory_holds(outputs: tuple[Path, Path]) -> None:
    result = receive(outputs, event())
    assert result.case_id
    (outputs[1] / result.case_id / "confirmed").mkdir()
    assert receive(outputs, event()).status == "HOLD"


def test_io_error_is_safe(
    outputs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("untrusted-sensitive-detail")

    monkeypatch.setattr(intake, "roots", fail)
    result = receive(outputs, event())
    assert result.status == "HOLD" and "sensitive" not in repr(result)


def test_credentials_in_metadata_and_document_hold(outputs: tuple[Path, Path]) -> None:
    data = event()
    data["message"]["from"] = {"token": "ignored-secret-value"}
    assert receive(outputs, data).status == "HOLD"
    body = b"%PDF-" + b"123456:" + b"x" * 25
    assert receive(outputs, event("pdf", body), body).status == "HOLD"


def test_oversized_inputs_hold(
    outputs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(intake, "MAX_BYTES", 500)
    body = b"%PDF-" + b"x" * 501
    assert receive(outputs, event("pdf", body), body).status == "HOLD"
    assert (
        receive(outputs, {"update_id": 1, "message": {"text": "x" * 501}}).status
        == "HOLD"
    )


@pytest.mark.parametrize("location", ["text", "nested"])
def test_json_escaped_credentials_rejected(
    outputs: tuple[Path, Path], location: str
) -> None:
    marker = "123456:" + "x" * 25
    data = event()
    if location == "text":
        data["message"]["text"] = marker
    else:
        data["message"]["from"] = {"nested": [marker]}
    raw = intake.encode(data).replace(
        marker.encode(), ("123456:\\u0078" + "x" * 24).encode()
    )
    assert not intake.TOKEN_PATTERN.search(raw)
    result = intake.receive_event(
        raw_update=raw,
        policy=intake.TelegramPolicy(777, frozenset({-1001})),
        receipt_root=outputs[0],
        case_root=outputs[1],
    )
    assert result.status == "HOLD"
    assert not list(outputs[0].iterdir())
