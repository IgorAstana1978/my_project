"""Offline contract checks for the authorized WU11 TEST-only transport."""

import copy
import gc
import hashlib
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
import wu11_telegram_transport as transport  # type: ignore[import-not-found]
from test_extract_mixed_source_composition import (
    standard_row,
    text_page,
    write_spec_workbook,
    write_text_pdf,
)


def event(update_id: int = 1, chat_id: int = 123) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1780000000,
            "chat": {"id": chat_id, "type": "private"},
            "text": transport.MARKER,
        },
    }


def response(value: Any) -> bytes:
    return json.dumps({"ok": True, "result": value}).encode()


@pytest.mark.parametrize("reversed_keys", [False, True])
def test_exact_raw_update_preserved(reversed_keys: bool) -> None:
    raw = b'{ "update_id" : 1, "message" : {"text":"\\u041f"}}'
    wrapper = (
        b'{"result":[' + raw + b'], "ok":true}'
        if reversed_keys
        else b'{"ok":true, "result":[' + raw + b"]}"
    )
    assert transport.exact_updates(wrapper) == [raw]
    assert transport.exact_updates(response([])) == []


@pytest.mark.parametrize(
    "raw",
    [
        b"not-json",
        b'{"ok":false,"description":"unsafe"}',
        b'{"ok":true,"result":[],"extra":1}',
        b'{"ok":true,"result":[],"ok":true}',
        b'{"ok":true,"result":{}}',
        b'{"ok":true,"result":[1]}',
        response([{}] * 101),
        response({"password": "opaque"}),
    ],
)
def test_bad_api_response_holds(raw: bytes) -> None:
    with pytest.raises(transport.TelegramHold):
        transport.exact_updates(raw)


def test_discovery_exactly_one_chat_and_message() -> None:
    raw = json.dumps(event()).encode()
    assert transport.discover([raw]) == (raw, 123)
    for events in ([], [raw, raw], [raw, json.dumps(event(2, 456)).encode()]):
        with pytest.raises(transport.TelegramHold):
            transport.discover(events)


def test_discovery_optional_start_then_marker() -> None:
    activation = event()
    activation["message"]["text"] = "/start"
    start_raw = json.dumps(activation).encode()
    marker_raw = json.dumps(event(2)).encode()
    assert transport.discover([start_raw, marker_raw]) == (marker_raw, 123)


@pytest.mark.parametrize("redelivery", [False, True])
def test_discovery_pending_start_preserves_binding(redelivery: bool) -> None:
    activation = event(10)
    activation["message"]["text"] = "/start"
    activation["message"]["entities"] = [
        {"offset": 0, "length": 6, "type": "bot_command"}
    ]
    activation["message"]["from"] = {"id": 123, "is_bot": False}
    raw = json.dumps(activation).encode()
    captured: dict[int, bytes] = {}
    assert transport.discover([raw], captured) == (None, 123)
    assert captured == {10: raw}
    assert transport.discover([raw], captured) == (None, 123)
    marker = json.dumps(event(11)).encode()
    assert transport.discover(([raw] if redelivery else []) + [marker], captured) == (
        marker,
        123,
    )
    assert captured == {10: raw}


@pytest.mark.parametrize(
    "failure",
    [
        "wrong_text",
        "payload",
        "suffix",
        "caption",
        "document",
        "photo",
        "service",
        "entities",
        "bot_sender",
        "bad_sender",
        "credential",
        "duplicate_start",
        "new_start",
        "duplicate_marker",
        "duplicate_id",
        "foreign",
        "marker_first",
        "update_order",
        "message_order",
        "date_order",
    ],
)
def test_discovery_invalid_inputs_hold_without_capturing(failure: str) -> None:
    activation = event(10)
    activation["message"]["text"] = "/start"
    marker = event(11)
    message = activation["message"]
    events = [activation, marker]
    if failure in {"wrong_text", "payload", "suffix"}:
        message["text"] = {
            "wrong_text": "hello",
            "payload": "/start payload",
            "suffix": "/start@bot",
        }[failure]
    elif failure in {"caption", "document", "photo", "service"}:
        message[
            {
                "caption": "caption",
                "document": "document",
                "photo": "photo",
                "service": "new_chat_members",
            }[failure]
        ] = "unsupported"
    elif failure == "entities":
        message["entities"] = [{"offset": 0, "length": 6, "type": "url"}]
    elif failure in {"bot_sender", "bad_sender"}:
        message["from"] = {"id": 123, "is_bot": True} if failure == "bot_sender" else []
    elif failure == "credential":
        message["from"] = {"id": 123, "is_bot": False, "password": "opaque"}
    elif failure == "duplicate_start":
        events = [activation, activation, marker]
    elif failure == "new_start":
        second = copy.deepcopy(activation)
        second["update_id"] = second["message"]["message_id"] = 11
        events = [activation, second, event(12)]
    elif failure == "duplicate_marker":
        events.append(event(12))
    elif failure == "duplicate_id":
        marker["update_id"] = 10
    elif failure == "foreign":
        marker["message"]["chat"]["id"] = 456
    elif failure == "marker_first":
        events.reverse()
    elif failure == "update_order":
        marker["update_id"] = 9
    elif failure == "message_order":
        marker["message"]["message_id"] = 9
    else:
        marker["message"]["date"] -= 1
    captured: dict[int, bytes] = {}
    with pytest.raises(transport.TelegramHold):
        transport.discover([json.dumps(data).encode() for data in events], captured)
    assert captured == {}


@pytest.mark.parametrize("failure", ["foreign", "changed", "new_start", "older_marker"])
def test_discovery_pending_rejects_conflicts(failure: str) -> None:
    activation = event(10)
    activation["message"]["text"] = "/start"
    raw = json.dumps(activation).encode()
    captured: dict[int, bytes] = {}
    assert transport.discover([raw], captured) == (None, 123)
    candidate = event(11)
    if failure == "foreign":
        candidate["message"]["chat"]["id"] = 456
    elif failure == "changed":
        candidate = copy.deepcopy(activation)
        candidate["message"]["date"] += 1
    elif failure == "new_start":
        candidate["message"]["text"] = "/start"
    else:
        candidate = event(9)
    with pytest.raises(transport.TelegramHold):
        transport.discover([json.dumps(candidate).encode()], captured)
    assert captured == {10: raw}


@pytest.mark.parametrize(
    "failure", ["foreign", "wrong_text", "duplicate", "service", "pending_exhausted"]
)
def test_live_discovery_hold_creates_no_intake_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    receipts, cases = tmp_path / "receipts", tmp_path / "cases"
    monkeypatch.setattr(transport, "RECEIPTS", receipts)
    monkeypatch.setattr(transport, "CASES", cases)
    monkeypatch.setattr(
        transport, "hidden_token", lambda: "opaque-synthetic-credential"
    )
    activation = event()
    activation["message"]["text"] = "/start"
    marker = event(2)
    events = [activation, marker]
    if failure == "foreign":
        marker["message"]["chat"]["id"] = 456
    elif failure == "wrong_text":
        activation["message"]["text"] = "/start payload"
    elif failure == "duplicate":
        events.insert(0, activation)
    elif failure == "pending_exhausted":
        events = [activation]
    else:
        activation["message"]["new_chat_members"] = []
    calls: list[str] = []

    class FakeAPI:
        def __init__(self, _: str) -> None:
            pass

        def call(self, method: str, parameters: dict[str, str] | None = None) -> bytes:
            calls.append(method)
            assert method in {"getMe", "getUpdates"}
            return response(
                {"username": transport.BOT, "is_bot": True, "id": 777}
                if method == "getMe"
                else events
            )

    class Coordination:
        def readline(self) -> str:
            return "poll\n"

    def reject_intake(*args: Any, **kwargs: Any) -> None:
        pytest.fail("activation or invalid discovery reached governed intake")

    monkeypatch.setattr(transport, "BotAPI", FakeAPI)
    monkeypatch.setattr(transport.sys, "stdin", Coordination())
    monkeypatch.setattr(transport, "receive_event", reject_intake)
    with pytest.raises(transport.TelegramHold):
        transport.live()
    assert calls == ["getMe"] + ["getUpdates"] * (
        3 if failure == "pending_exhausted" else 1
    )
    assert not list(receipts.iterdir())
    assert not list(cases.iterdir())


@pytest.mark.parametrize("change", ["wrong_id", "edited", "credentials", "chat"])
def test_bad_identity_is_safe(change: str) -> None:
    data = event()
    if change == "wrong_id":
        data["update_id"] = True
    elif change == "edited":
        data["edited_message"] = data.pop("message")
    elif change == "credentials":
        data["message"]["secret"] = "opaque"
    else:
        data["message"]["chat"] = None
    with pytest.raises(transport.TelegramHold):
        transport.identity(json.dumps(data).encode())


def test_roots_create_and_existing_contents_hold(tmp_path: Path) -> None:
    receipts, cases = tmp_path / "receipts", tmp_path / "cases"
    transport.initialize_roots(receipts, cases)
    (receipts / "unexpected").write_bytes(b"preserve")
    with pytest.raises(transport.TelegramHold):
        transport.initialize_roots(receipts, cases)
    assert (receipts / "unexpected").read_bytes() == b"preserve"


def known_fixture_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    if sys.platform != "win32":
        pytest.skip("the approved cache contains a Windows Junction")
    import _winapi

    receipts, cases = tmp_path / "receipts", tmp_path / "cases"
    cache = receipts / "_smoke-fixtures"
    cache.mkdir(parents=True)
    cases.mkdir()
    names = (
        "wu11-smoke.pdf",
        "wu11-smoke.xlsx",
        "create-smoke.mjs",
        "wu11-smoke-pdf.png",
        "wu11-smoke-xlsx.png",
        ".wu11-export.tmp.inspect.ndjson",
    )
    hashes = {}
    for name in names:
        body = f"synthetic inert fixture: {name}".encode()
        (cache / name).write_bytes(body)
        hashes[name] = hashlib.sha256(body).hexdigest()
    target = tmp_path / "inert-authoring-target"
    target.mkdir()
    _winapi.CreateJunction(str(target), str(cache / "node_modules"))
    # Synthetic authority inputs: never read the real approved roots/target.
    monkeypatch.setattr(transport, "APPROVED_FIXTURE_HASHES", hashes, raising=False)
    monkeypatch.setattr(
        transport, "AUTHORING_JUNCTION_TARGET", str(target), raising=False
    )
    return receipts, cases


def cache_snapshot(receipts: Path, cases: Path) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}

    def capture(path: Path) -> None:
        if path.is_junction() or path.is_symlink():
            snapshot[str(path)] = (os.readlink(path), path.lstat().st_mtime_ns)
        elif path.is_file():
            snapshot[str(path)] = (path.read_bytes(), path.stat().st_mtime_ns)
        else:
            entries = sorted(path.iterdir())
            snapshot[str(path)] = (
                path.stat().st_mtime_ns,
                tuple(entry.name for entry in entries),
            )
            for entry in entries:
                capture(entry)

    for root in (receipts, cases):
        capture(root)
    return snapshot


def test_initialize_known_fixture_cache_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts, cases = known_fixture_cache(tmp_path, monkeypatch)
    before = cache_snapshot(receipts, cases)

    def no_mkdir(*args: Any, **kwargs: Any) -> None:
        pytest.fail("existing fixture-only initialization must be read-only")

    original_scandir = os.scandir

    def no_junction_traversal(path: Any) -> Any:
        assert Path(path) not in {
            receipts / "_smoke-fixtures" / "node_modules",
            tmp_path / "inert-authoring-target",
        }
        return original_scandir(path)

    monkeypatch.setattr(Path, "mkdir", no_mkdir)
    monkeypatch.setattr(os, "scandir", no_junction_traversal)
    transport.initialize_roots(receipts, cases)
    assert cache_snapshot(receipts, cases) == before


@pytest.mark.parametrize(
    "change",
    [
        "extra_receipt",
        "existing_case",
        "extra_cache_file",
        "missing_fixture",
        "changed_fixture",
        "changed_helper",
        "source_junction",
        "cache_junction",
        "root_junction",
        "wrong_junction_target",
        "regular_node_modules",
        "missing_junction",
    ],
)
def test_initialize_rejects_changed_cache_without_writes(
    change: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts, cases = known_fixture_cache(tmp_path, monkeypatch)
    cache = receipts / "_smoke-fixtures"
    junction = cache / "node_modules"
    import _winapi

    if change == "extra_receipt":
        (receipts / "previous-receipt").write_bytes(b"preserve receipt")
    elif change == "existing_case":
        (cases / "previous-case").write_bytes(b"preserve Case")
    elif change == "extra_cache_file":
        (cache / "unknown.txt").write_bytes(b"preserve unknown")
    elif change == "missing_fixture":
        (cache / "wu11-smoke.pdf").unlink()
    elif change in {"changed_fixture", "changed_helper"}:
        name = "wu11-smoke.xlsx" if change == "changed_fixture" else "create-smoke.mjs"
        (cache / name).write_bytes(b"changed synthetic bytes")
    elif change == "source_junction":
        (cache / "wu11-smoke.pdf").unlink()
        _winapi.CreateJunction(
            str(tmp_path / "inert-authoring-target"), str(cache / "wu11-smoke.pdf")
        )
    elif change in {"cache_junction", "root_junction"}:
        source = cache if change == "cache_junction" else receipts
        moved = tmp_path / "moved-synthetic-directory"
        source.rename(moved)
        _winapi.CreateJunction(str(moved), str(source))
    else:
        junction.rmdir()  # Removes only this synthetic Junction, never its target.
        if change == "wrong_junction_target":
            other = tmp_path / "other-inert-target"
            other.mkdir()
            _winapi.CreateJunction(str(other), str(junction))
        elif change == "regular_node_modules":
            junction.mkdir()
    before = cache_snapshot(receipts, cases)

    def no_mkdir(*args: Any, **kwargs: Any) -> None:
        pytest.fail("rejected initialization must not create directories")

    monkeypatch.setattr(Path, "mkdir", no_mkdir)
    with pytest.raises(transport.TelegramHold):
        transport.initialize_roots(receipts, cases)
    assert cache_snapshot(receipts, cases) == before


@pytest.mark.parametrize("path", ["../file", "/file", "a//b", "a?b", "a\\b", ""])
def test_download_path_holds_before_network(path: str) -> None:
    api = transport.BotAPI("opaque-synthetic-credential")
    with pytest.raises(transport.TelegramHold):
        api.download(path)


def test_api_allowlist_and_offset_prohibited(monkeypatch: pytest.MonkeyPatch) -> None:
    api = transport.BotAPI("opaque-synthetic-credential")
    calls: list[tuple[str, bytes | None]] = []

    def request(path: str, body: bytes | None = None) -> bytes:
        calls.append((path, body))
        return b"safe"

    monkeypatch.setattr(api, "_request", request)
    assert api.call("getUpdates", {"limit": "100", "timeout": "0"}) == b"safe"
    assert calls[0][1] == b"limit=100&timeout=0"
    for method in ("sendMessage", "sendDocument", "setWebhook"):
        with pytest.raises(transport.TelegramHold):
            api.call(method)
    for parameters in ({"offset": "2"}, {"allowed_updates": "[]"}):
        with pytest.raises(transport.TelegramHold):
            api.call("getUpdates", parameters)
    assert len(calls) == 1


def test_real_extractor_duplicates_and_local_rejections(tmp_path: Path) -> None:
    receipts, cases = tmp_path / "receipts", tmp_path / "cases"
    transport.initialize_roots(receipts, cases)
    policy = transport.TelegramPolicy(777, frozenset({123}))
    data = event()
    raw = json.dumps(data).encode()
    evidence = transport.deliver(raw, policy, receipts, cases)
    assert evidence["engineering_items"] == 0
    assert evidence["duplicate_no_overwrite"]
    assert evidence["stop_before"] == "HUMAN_APPROVAL_1"
    for change in ("chat", "text"):
        changed = copy.deepcopy(data)
        if change == "chat":
            changed["message"]["chat"]["id"] = 456
        else:
            changed["message"]["text"] = "changed-redelivery"
        with pytest.raises(transport.TelegramHold):
            transport.deliver(json.dumps(changed).encode(), policy, receipts, cases)
    receipt = receipts / evidence["case_id"] / "text.txt"
    receipt.write_bytes(b"local-tamper")
    with pytest.raises(transport.TelegramHold):
        transport.deliver(raw, policy, receipts, cases)


@pytest.mark.parametrize("kind", ["pdf", "xlsx"])
def test_live_rejects_fixture_replaced_after_initialization(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts, cases = known_fixture_cache(tmp_path, monkeypatch)
    monkeypatch.setattr(transport, "RECEIPTS", receipts)
    monkeypatch.setattr(transport, "CASES", cases)
    monkeypatch.setattr(
        transport, "hidden_token", lambda: "opaque-synthetic-credential"
    )
    calls: list[str] = []
    changed_fixture = receipts / transport.FIXTURES / f"wu11-smoke.{kind}"

    class FakeAPI:
        def __init__(self, _: str) -> None:
            pass

        def call(self, method: str, parameters: dict[str, str] | None = None) -> bytes:
            calls.append(method)
            if method == "getMe":
                return response({"username": transport.BOT, "is_bot": True, "id": 777})
            if calls == ["getMe", "getUpdates"]:
                return response([event()])
            pytest.fail("replaced fixture reached document polling or getFile")

        def download(self, path: str) -> bytes:
            pytest.fail("replaced fixture reached download")

    class Coordination:
        def readline(self) -> str:
            # live() already checked the original synthetic cache in initialize_roots.
            changed_fixture.write_bytes(b"replaced synthetic fixture after init")
            return "poll\n"

    monkeypatch.setattr(transport, "BotAPI", FakeAPI)
    monkeypatch.setattr(transport.sys, "stdin", Coordination())
    with pytest.raises(
        transport.TelegramHold, match="approved TEST fixture hash changed"
    ):
        transport.live()
    assert calls == ["getMe", "getUpdates"]
    assert changed_fixture.read_bytes() == b"replaced synthetic fixture after init"
    assert len(list(cases.iterdir())) == 1
    assert not list(cases.rglob("*.pdf"))
    assert not list(cases.rglob("*.xlsx"))


@pytest.mark.parametrize(
    ("activation_mode", "queue_fault"),
    [
        ("direct", None),
        ("batch", None),
        ("pending", None),
        ("pending", "pdf_changed"),
        ("pending", "xlsx_changed"),
        ("pending", "pdf_duplicate"),
        ("pending", "xlsx_duplicate"),
        ("pending", "pdf_foreign"),
        ("pending", "pdf_new_start"),
        ("pending", "pdf_older"),
    ],
)
def test_mocked_full_pilot_preserves_captions_and_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    activation_mode: str,
    queue_fault: str | None,
) -> None:
    receipts, cases = tmp_path / "receipts", tmp_path / "cases"
    monkeypatch.setattr(transport, "RECEIPTS", receipts)
    monkeypatch.setattr(transport, "CASES", cases)
    monkeypatch.setattr(
        transport, "hidden_token", lambda: "opaque-synthetic-credential"
    )
    batches: list[list[dict[str, Any]]] = []
    bodies: dict[str, bytes] = {}

    class FakeAPI:
        def __init__(self, _: str) -> None:
            pass

        def call(self, method: str, parameters: dict[str, str] | None = None) -> bytes:
            if method == "getMe":
                return response({"username": transport.BOT, "is_bot": True, "id": 777})
            if method == "getUpdates":
                return response(batches.pop(0))
            assert method == "getFile" and parameters
            body = bodies[parameters["file_id"]]
            return response(
                {
                    "file_id": parameters["file_id"],
                    "file_unique_id": parameters["file_id"],
                    "file_size": len(body),
                    "file_path": parameters["file_id"],
                }
            )

        def download(self, path: str) -> bytes:
            return bodies[path]

    monkeypatch.setattr(transport, "BotAPI", FakeAPI)
    fixture_root = tmp_path / "fixture-staging"
    fixture_root.mkdir()
    pdf = write_text_pdf(fixture_root / "wu11-smoke.pdf", [text_page()])
    xlsx = write_spec_workbook(
        fixture_root / "wu11-smoke.xlsx", {"Spec": [standard_row()]}
    )
    monkeypatch.setattr(
        transport,
        "APPROVED_FIXTURE_HASHES",
        {
            fixture.name: hashlib.sha256(fixture.read_bytes()).hexdigest()
            for fixture in (pdf, xlsx)
        },
    )
    start = event()
    start["message"]["text"] = "/start"
    events = [] if activation_mode == "direct" else [start]
    if activation_mode == "pending":
        batches.append(list(events))
    events.append(event(len(events) + 1))
    batches.append(list(events))
    for index, fixture in enumerate((pdf, xlsx), start=len(events) + 1):
        bodies[fixture.name] = fixture.read_bytes()
        data = event(index)
        data["message"].pop("text")
        data["message"]["caption"] = "SYNTHETIC caption: choose a different model"
        data["message"]["document"] = {
            "file_id": fixture.name,
            "file_unique_id": fixture.name,
            "file_size": len(bodies[fixture.name]),
            "file_name": fixture.name,
        }
        events.append(data)
        batch = copy.deepcopy(events)
        if queue_fault and queue_fault.startswith(fixture.suffix[1:] + "_"):
            if queue_fault.endswith("changed"):
                batch[0]["message"]["date"] += 1
            elif queue_fault.endswith("duplicate"):
                batch.insert(1, copy.deepcopy(batch[0]))
            elif queue_fault.endswith("foreign"):
                batch[0]["message"]["chat"]["id"] = 456
            elif queue_fault.endswith("older"):
                batch = [data]
                data["update_id"] = 0
            else:
                extra_start = event(index + 1)
                extra_start["message"]["text"] = "/start"
                batch.append(extra_start)
        batches.append(batch)

    class Coordination:
        def readline(self) -> str:
            if not (receipts / transport.FIXTURES).exists():
                target = receipts / transport.FIXTURES
                target.mkdir()
                for fixture in (pdf, xlsx):
                    (target / fixture.name).write_bytes(fixture.read_bytes())
            return "poll\n"

    monkeypatch.setattr(transport.sys, "stdin", Coordination())
    assert transport.main() == (2 if queue_fault else 0)
    output = capsys.readouterr().out
    assert "opaque-synthetic-credential" not in output
    assert ("LIVE_SMOKE_PASS_STOP_BEFORE_HUMAN_APPROVAL_1" in output) is (
        queue_fault is None
    )
    expected_cases = (
        1
        if queue_fault and queue_fault.startswith("pdf")
        else (2 if queue_fault else 3)
    )
    assert len(list(cases.iterdir())) == expected_cases
    if activation_mode == "pending":
        assert "MARKER_NOT_YET_RECEIVED" in output
    if not queue_fault:
        assert not batches
    updates = [json.loads(path.read_bytes()) for path in receipts.rglob("update.json")]
    assert len(updates) == expected_cases
    assert all(update["message"].get("text") != "/start" for update in updates)
    for case in cases.iterdir():
        draft = json.loads((case / "preliminary-composition-draft.json").read_bytes())
        assert "choose a different model" not in json.dumps(draft)


def test_unknown_exception_never_printed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail() -> None:
        raise RuntimeError("opaque-synthetic-credential-in-URL")

    monkeypatch.setattr(transport, "live", fail)
    assert transport.main() == 2
    assert "opaque-synthetic-credential" not in capsys.readouterr().out


@pytest.mark.parametrize("failure", [None, "redirect", "oversized", "connection"])
def test_http_security_and_safe_diagnostics(
    failure: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(transport, "MAX_BYTES", 8)

    class Reply:
        status = 302 if failure == "redirect" else 200

        def read(self, limit: int) -> bytes:
            assert limit == 9
            return b"x" * (9 if failure == "oversized" else 1)

    class Connection:
        def __init__(self, host: str, *, timeout: int) -> None:
            assert host == "api.telegram.org" and timeout == 15

        def request(self, *args: Any, **kwargs: Any) -> None:
            calls.append((args, kwargs))
            if failure == "connection":
                raise OSError("opaque-sensitive-URL-error")

        def getresponse(self) -> Reply:
            return Reply()

        def close(self) -> None:
            calls.append("closed")

    monkeypatch.setattr(transport.http.client, "HTTPSConnection", Connection)
    api = transport.BotAPI("opaque-synthetic-credential")
    if failure:
        with pytest.raises(transport.TelegramHold) as caught:
            api.call("getMe")
        assert "opaque" not in str(caught.value)
        assert caught.value.__suppress_context__
    else:
        assert api.call("getMe") == b"x"
    assert calls[-1] == "closed"


@pytest.mark.parametrize("value", [None, "invalid", "valid"])
def test_hidden_input_is_masked_and_process_local(
    value: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tkinter as tk
    from tkinter import simpledialog

    class Root:
        def withdraw(self) -> None:
            pass

        def destroy(self) -> None:
            pass

        def bind_all(self, *args: Any, **kwargs: Any) -> None:
            assert args[0] == "<Map>"

    expected = "1" * 5 + chr(58) + "x" * 20

    def ask(*args: Any, **kwargs: Any) -> str | None:
        assert kwargs["show"] == "*"
        return expected if value == "valid" else value

    monkeypatch.setattr(tk, "Tk", Root)
    monkeypatch.setattr(simpledialog, "askstring", ask)
    if value == "valid":
        assert transport.hidden_token() == expected
    else:
        with pytest.raises(transport.TelegramHold):
            transport.hidden_token()
    assert transport.SECRET_ENV not in transport.os.environ


@pytest.mark.skipif(
    sys.platform != "win32", reason="Windows-only local masked-input diagnostic"
)
@pytest.mark.parametrize(
    "case",
    ["clean", "leading_space", "trailing_space", "crlf", "empty", "cancel"],
)
def test_actual_masked_dialog_with_synthetic_input_only(
    case: str, monkeypatch: pytest.MonkeyPatch, actual_tk_root: Any
) -> None:
    """Exercise actual Tk OK/cancel; no clipboard, real input, or network access."""
    import tkinter as tk
    from tkinter import simpledialog

    dummy = "1" * 5 + chr(58) + "x" * 20
    supplied = {
        "clean": dummy,
        "leading_space": " " + dummy,
        "trailing_space": dummy + " ",
        "crlf": dummy + "\r\n",
        "empty": "",
        "cancel": dummy,
    }[case]
    observed: dict[str, Any] = {}
    monkeypatch.setattr(tk, "Tk", lambda: actual_tk_root)
    monkeypatch.setattr(actual_tk_root, "destroy", lambda: None)
    query_string = cast(Any, simpledialog)._QueryString
    original_body = query_string.body

    def automated_body(dialog: Any, master: Any) -> Any:
        widget = original_body(dialog, master)
        dialog.title("WU11 SYNTHETIC DIAGNOSTIC - NO MANUAL INPUT")
        widget.insert(0, supplied)
        # No human keystroke or real credential can enter this test field.
        widget.configure(state="disabled")
        observed["masked"] = widget.cget("show") == "*"

        attempts = 0

        def finish() -> None:
            nonlocal attempts
            attempts += 1
            if not dialog.winfo_viewable():
                if attempts >= 100:
                    observed["visibility_timeout"] = True
                    dialog.cancel()
                    return
                dialog.after(50, finish)
                return
            if case == "cancel":
                dialog.cancel()
            else:
                dialog.ok()

        dialog.after(200, finish)
        return widget

    monkeypatch.setattr(query_string, "body", automated_body)
    if case == "clean":
        assert transport.hidden_token() == dummy
    else:
        with pytest.raises(
            transport.TelegramHold,
            match="^hidden secret input cancelled or invalid$",
        ):
            transport.hidden_token()
    assert observed == {"masked": True}
    assert transport.SECRET_ENV not in transport.os.environ


@pytest.fixture(scope="module")
def actual_tk_root() -> Iterator[Any]:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    try:
        yield root
    finally:
        root.destroy()
        # Dialog callbacks retain widget cycles and their thread-bound Tcl refs.
        # Release these on the creating thread before later tests start workers.
        gc.collect()
        # Pytest may retain the Python root after this fixture has finished.
        # Its native Tcl interpreter must be released on the creating thread.
        cast(Any, root).tk = None


@pytest.mark.skipif(
    sys.platform != "win32", reason="Windows-only local keyboard-layout diagnostic"
)
@pytest.mark.parametrize("fixed", [False, True])
def test_synthetic_ctrl_v_russian_layout_diagnostic(
    actual_tk_root: Any, fixed: bool
) -> None:
    """Reproduce physical Ctrl+V; replace Tk's selection getter with dummy data."""
    import ctypes
    import tkinter as tk

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetKeyboardLayoutList.argtypes = [
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    user32.GetKeyboardLayoutList.restype = ctypes.c_int
    user32.GetKeyboardLayout.argtypes = [ctypes.c_uint]
    user32.GetKeyboardLayout.restype = ctypes.c_void_p
    user32.ActivateKeyboardLayout.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.ActivateKeyboardLayout.restype = ctypes.c_void_p
    count = user32.GetKeyboardLayoutList(0, None)
    handles = (ctypes.c_void_p * count)()
    assert user32.GetKeyboardLayoutList(count, handles) == count
    layouts = {int(handle) & 0xFFFF: handle for handle in handles if handle}
    if not {0x409, 0x419} <= layouts.keys():
        pytest.skip("Both existing EN-US/RU layouts are required; no layout installed")
    original_layout = user32.GetKeyboardLayout(0)
    root = actual_tk_root
    dummy = "1" * 5 + chr(58) + "x" * 20
    selection_reads: list[str] = []

    def synthetic_selection(widget: str, selection: str) -> str:
        assert selection == "CLIPBOARD"
        selection_reads.append(selection)
        return dummy

    # This is an interpreter-local stub. No system clipboard call occurs.
    original_getter = "::tk::WU11OriginalGetSelection"
    root.tk.call("rename", "::tk::GetSelection", original_getter)
    root.tk.createcommand("::tk::GetSelection", synthetic_selection)
    original_map = root.bind_all("<Map>")
    root.unbind_all("<Map>")
    if fixed:
        transport._bind_local_paste(root)
    dialog = tk.Toplevel(root)
    dialog.title("WU11 SYNTHETIC KEYBOARD DIAGNOSTIC - NO MANUAL INPUT")
    entry = tk.Entry(dialog, show="*", state="disabled")
    entry.pack()
    observed: dict[str, Any] = {}

    def probe() -> None:
        try:
            for label, language in (("en", 0x409), ("ru", 0x419)):
                assert user32.ActivateKeyboardLayout(layouts[language], 0)
                entry.focus_force()
                dialog.update()
                assert int(user32.GetKeyboardLayout(0)) & 0xFFFF == language
                seen: list[tuple[int, bool]] = []
                entry.configure(state="normal")
                entry.delete(0, "end")
                selection_reads.clear()

                def record(event: Any, captured: list[tuple[int, bool]] = seen) -> None:
                    captured.append((event.keycode, bool(event.state & 0x0004)))

                binding = entry.bind("<KeyPress>", record)
                entry.event_generate("<KeyPress>", keycode=0x56, state=0x0004)
                entry.unbind("<KeyPress>", binding)
                observed[label] = {
                    "physical_key": seen,
                    "paste_calls": len(selection_reads),
                    "dummy_received": entry.get() == dummy,
                    "empty": entry.get() == "",
                }
                entry.configure(state="disabled")
        except Exception as error:
            observed["probe_error"] = type(error).__name__
        finally:
            user32.ActivateKeyboardLayout(original_layout, 0)
            dialog.destroy()

    try:
        dialog.after(200, probe)
        root.wait_window(dialog)
    finally:
        user32.ActivateKeyboardLayout(original_layout, 0)
        root.tk.deletecommand("::tk::GetSelection")
        root.tk.call("rename", original_getter, "::tk::GetSelection")
        root.tk.call("bind", "all", "<Map>", original_map)
    expected_physical = [] if fixed else [(0x56, True)]
    assert observed == {
        "en": {
            "physical_key": expected_physical,
            "paste_calls": 1,
            "dummy_received": True,
            "empty": False,
        },
        "ru": {
            "physical_key": expected_physical,
            "paste_calls": 1 if fixed else 0,
            "dummy_received": fixed,
            "empty": not fixed,
        },
    }
