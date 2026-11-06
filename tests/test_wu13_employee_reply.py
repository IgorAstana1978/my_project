"""Operator-confirmed reply to the same private chat (Igor's decision 2026-11-06)."""

import io
import json
from pathlib import Path
from typing import Any, cast

import pytest
import wu13_employee_telegram as op  # type: ignore[import-not-found]
from test_wu13_employee_telegram import API, config, dispositions, event, run

__all__ = ["config"]


@pytest.fixture
def send_config(config: op.Config, tmp_path: Path) -> op.Config:
    outbox = tmp_path / "outbox"
    outbox.mkdir()
    data = json.loads(config.path.read_bytes())
    data["profile"] = op.PROFILE_SEND
    data["outbox_root"] = str(outbox)
    config.path.write_bytes(op.encode(data))
    return op.Config.read(config.path)


class SendAPI(API):
    def __init__(self, config: op.Config, batches: list[list[dict[str, Any]]]) -> None:
        super().__init__(config, batches)
        self.sent: list[tuple[int, int, str, bytes]] = []
        self.fail = False
        self.wrong_chat = False

    def send_document(
        self, chat_id: int, reply_to: int, name: str, body: bytes
    ) -> bytes:
        if self.fail:
            raise op.TelegramHold("synthetic transport failure")
        self.sent.append((chat_id, reply_to, name, body))
        chat = chat_id + 1 if self.wrong_chat else chat_id
        result = {"chat": {"id": chat}, "document": {"file_id": "x"}}
        return cast(bytes, op.encode({"ok": True, "result": result}))

    def send_message(self, chat_id: int, reply_to: int, text: str) -> bytes:
        if self.fail:
            raise op.TelegramHold("synthetic transport failure")
        self.sent.append((chat_id, reply_to, "TEXT", text.encode()))
        chat = chat_id + 1 if self.wrong_chat else chat_id
        result = {"chat": {"id": chat}, "text": text}
        return cast(bytes, op.encode({"ok": True, "result": result}))


def accepted_case(config: op.Config, monkeypatch: pytest.MonkeyPatch) -> str:
    data = event(5)
    data["message"]["chat"]["id"] = data["message"]["from"]["id"] = 456
    run(config, SendAPI(config, [[data]]), monkeypatch, "poll\nstop\n")
    return cast(str, dispositions(config)[5]["data"]["case_id"])


def prepare(config: op.Config, case_id: str, names: list[str]) -> Path:
    assert config.outbox is not None
    folder: Path = config.outbox / case_id
    folder.mkdir()
    for name in names:
        (folder / name).write_bytes(b"SYNTHETIC " + name.encode())
    return folder


def events(config: op.Config) -> list[str]:
    return [r["event"] for r in op.Journal(config).records]


def test_send_after_confirm_to_request_chat_once(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = accepted_case(send_config, monkeypatch)
    folder = prepare(send_config, case_id, ["КП №463-1.pdf", "КП №463-1.xlsx"])
    api = SendAPI(send_config, [])
    run(send_config, api, monkeypatch, f"send {case_id}\nconfirm\nstop\n")
    assert [(c, r, n) for c, r, n, _ in api.sent] == [
        (456, 5, "КП №463-1.xlsx"),
        (456, 5, "КП №463-1.pdf"),
    ]
    assert events(send_config)[-2:] == ["SEND_INTENT", "SENT"]
    assert [m for m, _ in api.calls] == ["getMe"]
    # A second send is refused; a restart verifies the sent files are unchanged.
    again = SendAPI(send_config, [])
    run(send_config, again, monkeypatch, f"send {case_id}\nstop\n")
    assert not again.sent
    (folder / "КП №463-1.pdf").write_bytes(b"changed")
    restarted = SendAPI(send_config, [])
    with pytest.raises(op.TelegramHold):
        run(send_config, restarted, monkeypatch, "stop\n")
    assert not restarted.calls


@pytest.mark.parametrize(
    "fault", ["cancel", "unknown", "empty", "missing", "txt", "two_pdf", "subdir"]
)
def test_send_refused_without_sending(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    case_id = accepted_case(send_config, monkeypatch)
    names = {"txt": ["a.txt"], "two_pdf": ["a.pdf", "b.PDF"], "empty": []}
    if fault != "missing":
        folder = prepare(send_config, case_id, names.get(fault, ["a.xlsx"]))
        if fault == "subdir":
            (folder / "b.pdf").mkdir()
    target = "CASE-TELEGRAM-" + "A" * 64 if fault == "unknown" else case_id
    answer = "no\n" if fault == "cancel" else ""
    api = SendAPI(send_config, [])
    run(send_config, api, monkeypatch, f"send {target}\n{answer}stop\n")
    assert not api.sent
    assert "SEND_INTENT" not in events(send_config)


def test_receive_only_profile_never_sends(
    config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = accepted_case(config, monkeypatch)
    api = SendAPI(config, [])
    run(config, api, monkeypatch, f"send {case_id}\nstop\n")
    assert not api.sent
    assert "SEND_INTENT" not in events(config)


@pytest.mark.parametrize("fault", ["transport", "wrong_chat"])
def test_unconfirmed_send_holds_until_inspection(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    case_id = accepted_case(send_config, monkeypatch)
    prepare(send_config, case_id, ["a.xlsx"])
    api = SendAPI(send_config, [])
    api.fail = fault == "transport"
    api.wrong_chat = fault == "wrong_chat"
    with pytest.raises(op.TelegramHold):
        run(send_config, api, monkeypatch, f"send {case_id}\nconfirm\nstop\n")
    assert "SEND_INTENT" in events(send_config)
    assert "SENT" not in events(send_config)
    restarted = SendAPI(send_config, [])
    with pytest.raises(op.TelegramHold):
        run(send_config, restarted, monkeypatch, "stop\n")
    assert not restarted.calls


def test_files_changed_between_ready_and_confirm_hold(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = accepted_case(send_config, monkeypatch)
    path = prepare(send_config, case_id, ["a.xlsx"]) / "a.xlsx"

    class Stdin:
        def __init__(self, text: str) -> None:
            self.stream = io.StringIO(text)

        def readline(self) -> str:
            value = self.stream.readline()
            if value.strip() == "confirm":
                path.write_bytes(b"swapped")
            return value

    api = SendAPI(send_config, [])
    monkeypatch.setattr(op, "BotAPI", lambda _: api)
    monkeypatch.setattr(op, "hidden_token", lambda _: "opaque-synthetic-secret")
    monkeypatch.setattr(op.sys, "stdin", Stdin(f"send {case_id}\nconfirm\nstop\n"))
    with pytest.raises(op.TelegramHold):
        op.run(send_config)
    assert not api.sent
    assert "SEND_INTENT" not in events(send_config)


def test_tampered_reply_audit_holds(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = accepted_case(send_config, monkeypatch)
    prepare(send_config, case_id, ["a.xlsx"])
    run(
        send_config,
        SendAPI(send_config, []),
        monkeypatch,
        f"send {case_id}\nconfirm\nstop\n",
    )
    journal = op.Journal(send_config)
    journal.append("SENT", journal.records[-1]["data"])
    with pytest.raises(op.TelegramHold):
        op.Journal(send_config).replies()
    with pytest.raises(op.TelegramHold):
        op.Journal.validate("SENT", {"case_id": "x", "outbox_sha256": "0" * 64})


@pytest.mark.parametrize("where", ["receipts", "git", "missing", "relative", "number"])
def test_invalid_outbox_profile(send_config: op.Config, where: str) -> None:
    data = json.loads(send_config.path.read_bytes())
    data["outbox_root"] = {
        "receipts": str(send_config.receipts / "nested"),
        "git": str(Path(__file__).resolve().parent),
        "missing": str(send_config.receipts.parent / "absent"),
        "relative": "outbox",
        "number": 5,
    }[where]
    if where == "receipts":
        Path(data["outbox_root"]).mkdir()
    send_config.path.write_bytes(op.encode(data))
    with pytest.raises(op.TelegramHold):
        op.Config.read(send_config.path)


def test_v2_profile_requires_outbox(send_config: op.Config) -> None:
    data = json.loads(send_config.path.read_bytes())
    data.pop("outbox_root")
    send_config.path.write_bytes(op.encode(data))
    with pytest.raises(op.TelegramHold):
        op.Config.read(send_config.path)


@pytest.mark.parametrize("status", [200, 500])
def test_send_document_multipart_to_fixed_host(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    seen: dict[str, Any] = {}

    class Response:
        def __init__(self) -> None:
            self.status = status

        def read(self, size: int) -> bytes:
            return b'{"ok":true}'

    class Connection:
        def __init__(self, host: str, timeout: int) -> None:
            seen["host"] = host

        def request(self, method: str, path: str, body: bytes, headers: Any) -> None:
            seen.update(method=method, path=path, body=body, headers=headers)

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            seen["closed"] = True

    monkeypatch.setattr(op.http.client, "HTTPSConnection", Connection)
    api = op.BotAPI("opaque-synthetic-secret")
    if status != 200:
        with pytest.raises(op.TelegramHold):
            api.send_document(456, 5, "a.xlsx", b"x")
        assert seen["closed"]
        return
    assert api.send_document(456, 5, "КП.xlsx", b"BODY") == b'{"ok":true}'
    assert seen["host"] == "api.telegram.org" and seen["closed"]
    assert seen["path"].endswith("/sendDocument")
    body = seen["body"].decode()
    assert 'name="chat_id"\r\n\r\n456\r\n' in body
    assert '"message_id": 5' in body and 'filename="КП.xlsx"' in body
    assert "BODY" in body


def test_changed_quote_is_sent_again_as_next_revision(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Igor 2026-11-06: a changed quote is sent again, never an identical one."""
    case_id = accepted_case(send_config, monkeypatch)
    prepare(send_config, case_id, ["КП.pdf"])
    run(
        send_config,
        SendAPI(send_config, []),
        monkeypatch,
        f"send {case_id}\nconfirm\nstop\n",
    )
    assert send_config.outbox is not None
    second = send_config.outbox / f"{case_id}.2"
    second.mkdir()
    (second / "КП.pdf").write_bytes(
        b"SYNTHETIC " + "КП.pdf".encode()
    )  # same as revision 1
    same = SendAPI(send_config, [])
    run(send_config, same, monkeypatch, f"send {case_id}\nstop\n")
    assert not same.sent
    (second / "КП.pdf").write_bytes(b"CHANGED quote")
    api = SendAPI(send_config, [])
    run(send_config, api, monkeypatch, f"send {case_id}\nconfirm\nstop\n")
    assert [(c, r, n, b) for c, r, n, b in api.sent] == [
        (456, 5, "КП.pdf", b"CHANGED quote")
    ]
    records = op.Journal(send_config).records
    assert records[-1]["data"]["revision"] == 2 and records[-1]["event"] == "SENT"
    assert op.Journal(send_config).replies()[case_id].keys() == {1, 2}
    # No third folder: refused; a sent revision folder must stay unchanged.
    third = SendAPI(send_config, [])
    run(send_config, third, monkeypatch, f"send {case_id}\nstop\n")
    assert not third.sent
    (second / "КП.pdf").write_bytes(b"edited after sending")
    with pytest.raises(op.TelegramHold):
        run(send_config, SendAPI(send_config, []), monkeypatch, "stop\n")


@pytest.mark.parametrize("revision", [1, 0, 100, "2", True])
def test_invalid_reply_revision_record(revision: Any) -> None:
    data = {"case_id": "CASE-TELEGRAM-" + "A" * 64, "outbox_sha256": "0" * 64}
    with pytest.raises(op.TelegramHold):
        op.Journal.validate("SENT", {**data, "revision": revision})
    op.Journal.validate("SENT", {**data, "revision": 2})


def test_revision_out_of_order_holds(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = accepted_case(send_config, monkeypatch)
    journal = op.Journal(send_config)
    record = {"case_id": case_id, "outbox_sha256": "0" * 64, "revision": 2}
    journal.append("SEND_INTENT", record)
    with pytest.raises(op.TelegramHold, match="duplicate reply intent"):
        op.Journal(send_config).replies()


def test_too_many_revisions_refused(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = accepted_case(send_config, monkeypatch)
    sent = {r: f"{r:064x}" for r in range(1, op.MAX_REVISION + 1)}
    monkeypatch.setattr(op.Journal, "replies", lambda self: {case_id: sent})
    monkeypatch.setattr(op, "verify_local", lambda *a: None)
    api = SendAPI(send_config, [])
    op.reply(send_config, op.Journal(send_config), api, case_id, lambda: True)
    assert not api.sent
