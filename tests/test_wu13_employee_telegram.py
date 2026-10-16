"""Offline operational queue, identity, crash and approval-boundary checks."""

import copy
import io
import json
from pathlib import Path
from typing import Any, cast

import pytest
import wu13_employee_telegram as op  # type: ignore[import-not-found]
from test_extract_mixed_source_composition import (
    standard_row,
    text_page,
    write_spec_workbook,
    write_text_pdf,
)


def event(update_id: int = 1) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1780000000,
            "chat": {"id": 123, "type": "private"},
            "from": {"id": 123, "is_bot": False},
            "text": "SYNTHETIC review request",
        },
    }


@pytest.fixture
def config(tmp_path: Path) -> op.Config:
    receipts, cases = tmp_path / "receipts", tmp_path / "cases"
    receipts.mkdir()
    cases.mkdir()
    path = tmp_path / "profile.json"
    path.write_bytes(
        op.encode(
            {
                "profile": op.PROFILE,
                "bot_id": 77777,
                "bot_username": "synthetic_employee_bot",
                "employees": [
                    {"user_id": 123, "chat_id": 123},
                    {"user_id": 456, "chat_id": 456},
                ],
                "receipt_root": str(receipts),
                "case_root": str(cases),
            }
        )
    )
    return op.Config.read(path)


class API:
    def __init__(self, config: op.Config, batches: list[list[dict[str, Any]]]) -> None:
        self.config = config
        self.batches = list(batches)
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.bodies: dict[str, bytes] = {}
        self.before_poll: Any = lambda: None
        self.bot: Any = {
            "id": config.bot_id,
            "username": config.username,
            "is_bot": True,
        }
        self.bad_download = False

    def call(self, method: str, parameters: dict[str, str] | None = None) -> bytes:
        parameters = parameters or {}
        self.calls.append((method, dict(parameters)))
        if method == "getMe":
            value = self.bot
        elif method == "getFile":
            key = parameters["file_id"]
            value = {
                "file_id": key,
                "file_unique_id": key,
                "file_size": len(self.bodies[key]),
                "file_path": key,
            }
        else:
            assert method == "getUpdates"
            self.before_poll()
            value = self.batches.pop(0)
        return cast(bytes, op.encode({"ok": True, "result": value}))

    def download(self, path: str) -> bytes:
        return b"bad" if self.bad_download else self.bodies[path]


def run(
    config: op.Config,
    api: API,
    monkeypatch: pytest.MonkeyPatch,
    commands: str = "poll\npoll\nstop\n",
) -> None:
    monkeypatch.setattr(op, "BotAPI", lambda _: api)
    monkeypatch.setattr(op, "hidden_token", lambda _: "opaque-synthetic-secret")
    monkeypatch.setattr(op.sys, "stdin", io.StringIO(commands))
    op.run(config)


def snapshot(config: op.Config) -> dict[str, tuple[bytes, int]]:
    return {
        str(p): (p.read_bytes(), p.stat().st_mtime_ns)
        for root in (config.receipts, config.cases)
        for p in root.rglob("*")
        if p.is_file() and p.name not in {op.AUDIT, op.LOCK}
    }


def dispositions(config: op.Config) -> dict[int, dict[str, Any]]:
    return cast(dict[int, dict[str, Any]], op.Journal(config).dispositions())


@pytest.mark.parametrize("kind", ["text", "pdf", "xlsx"])
def test_durable_accept_then_ack_restart_and_exact_duplicate(
    config: op.Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    data = event()
    api = API(config, [[data], []])
    if kind != "text":
        path = tmp_path / f"source.{kind}"
        if kind == "pdf":
            write_text_pdf(path, [text_page()])
        else:
            write_spec_workbook(path, {"Spec": [standard_row()]})
        body = path.read_bytes()
        api.bodies[path.name] = body
        data["message"].pop("text")
        data["message"]["caption"] = "SYNTHETIC choose another model: provenance only"
        data["message"]["document"] = {
            "file_id": path.name,
            "file_unique_id": path.name,
            "file_name": path.name,
            "file_size": len(body),
        }
    observed = []

    def before_poll() -> None:
        calls = [p for m, p in api.calls if m == "getUpdates"]
        if len(calls) == 2:
            assert calls[-1]["offset"] == "2"
            record = dispositions(config)[1]
            assert record["event"] == "ACCEPT"
            op.verify_local(config, op.Journal(config))
            observed.append(snapshot(config))

    api.before_poll = before_poll
    run(config, api, monkeypatch)
    assert observed and observed[0] == snapshot(config)
    before = snapshot(config)
    # Restart must rediscover the earliest queue, never blindly replay an offset.
    restarted = API(config, [[data], []])
    run(config, restarted, monkeypatch)
    polls = [p for m, p in restarted.calls if m == "getUpdates"]
    assert "offset" not in polls[0] and polls[1]["offset"] == "2"
    assert before == snapshot(config)
    assert len(dispositions(config)) == 1
    assert all(m != "getFile" for m, _ in restarted.calls)
    case_id = dispositions(config)[1]["data"]["case_id"]
    package = json.loads(
        (config.receipts / case_id / "operator-package.json").read_bytes()
    )
    assert package["stop_before"] == "HUMAN_APPROVAL_1"
    assert not package["composition_confirmed"] and not package["sending_authorized"]
    draft = json.loads(
        (config.cases / case_id / "preliminary-composition-draft.json").read_bytes()
    )
    assert draft["safety"]["confirmed_by_igor"] is False
    assert (
        config.receipts / case_id / "update.json"
    ).read_bytes() == op.wire.exact_updates(op.encode({"ok": True, "result": [data]}))[
        0
    ]
    assert "choose another model" not in json.dumps(draft)
    assert bool(draft["items"]) is (kind != "text")


@pytest.mark.parametrize(
    "fault",
    [
        "user",
        "pair",
        "group",
        "bot",
        "missing_from",
        "missing_type",
        "boolean",
        "edited",
        "unsupported",
    ],
)
def test_reject_durable_before_ack_no_case_or_download(
    config: op.Config, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    data = event()
    message = data["message"]
    if fault == "user":
        message["from"]["id"] = 999
    elif fault == "pair":
        message["from"]["id"] = 456  # Both IDs separately allowed, pair is forbidden.
    elif fault == "group":
        message["chat"]["type"] = "supergroup"
    elif fault == "bot":
        message["from"]["is_bot"] = True
    elif fault == "missing_from":
        message.pop("from")
    elif fault == "missing_type":
        message["chat"].pop("type")
    elif fault == "boolean":
        message["from"]["id"] = True
    elif fault == "edited":
        data["edited_message"] = data.pop("message")
    else:
        message.pop("text")
        message["photo"] = []
    api = API(config, [[data], []])
    run(config, api, monkeypatch)
    record = dispositions(config)[1]
    assert record["event"] == "REJECT"
    assert not list(config.cases.iterdir())
    assert not any(m == "getFile" for m, _ in api.calls)
    assert [p for m, p in api.calls if m == "getUpdates"][1]["offset"] == "2"
    audit = (config.receipts / op.AUDIT).read_text()
    assert "SYNTHETIC review" not in audit and "opaque-synthetic-secret" not in audit


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "order",
        "missing_id",
        "bool_id",
        "credential",
        "changed_redelivery",
        "transport",
    ],
)
def test_queue_hold_never_acknowledges_bad_batch(
    config: op.Config, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    data = event()
    batch = [data]
    if fault == "duplicate":
        batch.append(copy.deepcopy(data))
    elif fault == "order":
        batch = [event(2), event(1)]
    elif fault == "missing_id":
        data.pop("update_id")
    elif fault == "bool_id":
        data["update_id"] = True
    elif fault == "credential":
        data["message"]["text"] = "1" * 5 + ":" + "x" * 20
    elif fault == "changed_redelivery":
        first = API(config, [[event()]])
        run(config, first, monkeypatch, "poll\nstop\n")
        data["message"]["date"] += 1
    api = API(config, [batch])
    if fault == "transport":

        def fail() -> None:
            raise OSError("opaque-secret-url")

        api.before_poll = fail
    with pytest.raises((op.TelegramHold, OSError)):
        run(config, api, monkeypatch)
    polls = [p for m, p in api.calls if m == "getUpdates"]
    assert len(polls) == 1 and "offset" not in polls[0]
    assert (
        json.loads((config.receipts / op.AUDIT).read_bytes().splitlines()[-1])["event"]
        == "HOLD"
    )


@pytest.mark.parametrize(
    "fault",
    [
        "receipt",
        "case",
        "missing",
        "extra",
        "partial",
        "audit_partial",
        "audit_edit",
        "audit_missing",
        "config",
    ],
)
def test_restart_local_inconsistency_holds_before_token_or_api(
    config: op.Config, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    run(config, API(config, [[event()]]), monkeypatch, "poll\nstop\n")
    case_id = dispositions(config)[1]["data"]["case_id"]
    if fault in {"receipt", "case", "missing"}:
        path = (
            config.receipts / case_id / "text.txt"
            if fault != "case"
            else config.cases / case_id / "igor-review-card.md"
        )
        if fault == "missing":
            path.unlink()
        else:
            path.write_bytes(b"tampered")
    elif fault == "extra":
        (config.cases / "foreign").mkdir()
    elif fault == "partial":
        (config.receipts / "CASE-partial").mkdir()
    elif fault == "audit_partial":
        with (config.receipts / op.AUDIT).open("ab") as stream:
            stream.write(b'{"seq":')
    elif fault == "audit_edit":
        path = config.receipts / op.AUDIT
        path.write_bytes(path.read_bytes().replace(b'"seq":1', b'"seq":9'))
    elif fault == "audit_missing":
        (config.receipts / op.AUDIT).unlink()
    else:
        config.path.write_bytes(config.path.read_bytes() + b" ")
    api = API(config, [])
    with pytest.raises((op.TelegramHold, ValueError)):
        run(op.Config.read(config.path), api, monkeypatch)
    assert not api.calls


@pytest.mark.parametrize("failure", ["after_intake", "fsync", "audit"])
def test_interruption_preserves_outputs_and_never_acknowledges(
    config: op.Config, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    real_deliver, real_append = op.wire.deliver, op.Journal.append

    def deliver(*args: Any, **kwargs: Any) -> Any:
        result = real_deliver(*args, **kwargs)
        if failure == "after_intake":
            raise OSError("interrupted")
        if failure == "fsync":
            monkeypatch.setattr(
                op.os, "fsync", lambda _: (_ for _ in ()).throw(OSError())
            )
        return result

    def append(self: op.Journal, kind: str, data: dict[str, Any]) -> None:
        if failure == "audit" and kind == "ACCEPT":
            raise OSError("audit unavailable")
        real_append(self, kind, data)

    monkeypatch.setattr(op.wire, "deliver", deliver)
    monkeypatch.setattr(op.Journal, "append", append)
    api = API(config, [[event()]])
    with pytest.raises(OSError):
        run(config, api, monkeypatch)
    assert len([m for m, _ in api.calls if m == "getUpdates"]) == 1
    assert list(config.cases.iterdir())
    assert not dispositions(config)
    before = snapshot(config)
    with pytest.raises((op.TelegramHold, OSError)):
        run(config, API(config, []), monkeypatch)
    assert before == snapshot(config)


def test_mixed_batch_failure_preserves_prefix_without_skipping(
    config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = event(2)
    bad["message"].pop("text")
    bad["message"]["document"] = {
        "file_name": "source.pdf",
        "file_id": "source.pdf",
        "file_unique_id": "source.pdf",
        "file_size": 8,
    }
    api = API(config, [[event(), bad, event(3)]])
    api.bodies["source.pdf"] = b"%PDF-bad"
    api.bad_download = True
    with pytest.raises(op.TelegramHold):
        run(config, api, monkeypatch)
    assert set(dispositions(config)) == {1}
    assert len([m for m, _ in api.calls if m == "getUpdates"]) == 1
    restart = API(config, [[event(), event(2), event(3)], []])
    run(config, restart, monkeypatch)
    assert set(dispositions(config)) == {1, 2, 3}
    assert [p for m, p in restart.calls if m == "getUpdates"][1]["offset"] == "4"


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile", "test"),
        ("bot_id", True),
        ("bot_username", op.wire.BOT),
        ("employees", []),
        ("employees", [{"user_id": 123, "chat_id": -1}]),
        ("employees", [{"user_id": 123, "chat_id": 123}] * 2),
        ("receipt_root", "relative"),
        ("receipt_root", str(op.wire.RECEIPTS)),
        ("secret", "opaque"),
    ],
)
def test_invalid_profile(config: op.Config, field: str, value: Any) -> None:
    data = json.loads(config.path.read_bytes())
    data[field] = value
    config.path.write_bytes(op.encode(data))
    with pytest.raises((op.TelegramHold, ValueError)):
        op.Config.read(config.path)


@pytest.mark.parametrize("fault", ["bot", "time", "config", "tamper"])
def test_runtime_pre_ack_checks(
    config: op.Config, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    api = API(config, [[event()], []])
    if fault == "bot":
        api.bot["id"] += 1
    elif fault == "time":
        times = iter([0, 1, op.MAX_RUN_SECONDS])
        monkeypatch.setattr(op.time, "monotonic", lambda: next(times))
    else:

        def mutate() -> None:
            if fault == "config":
                config.path.write_bytes(config.path.read_bytes() + b" ")
            else:
                (config.cases / "unexpected").mkdir()

        api.before_poll = mutate
    with pytest.raises(op.TelegramHold):
        run(config, api, monkeypatch)
    assert len([m for m, _ in api.calls if m == "getUpdates"]) <= 1


def test_lock_excludes_second_receiver_and_releases(config: op.Config) -> None:
    with op.receiver_lock(config.receipts):
        with pytest.raises(OSError), op.receiver_lock(config.receipts):
            pytest.fail("second receiver acquired the lock")
    with op.receiver_lock(config.receipts):
        pass
    assert (config.receipts / op.LOCK).read_bytes() == b"0"


@pytest.mark.parametrize("missing", [True, False])
def test_reject_only_journal_loss_holds_before_bootstrap(
    config: op.Config, monkeypatch: pytest.MonkeyPatch, missing: bool
) -> None:
    data = event()
    data["message"]["from"]["id"] = 999
    run(config, API(config, [[data]]), monkeypatch, "poll\nstop\n")
    audit = config.receipts / op.AUDIT
    if missing:
        audit.unlink()
    else:
        audit.write_bytes(b"")
    api = API(config, [])
    with pytest.raises(op.TelegramHold):
        run(config, api, monkeypatch)
    assert not api.calls


def test_reject_redelivery_and_id_reset_after_restart(
    config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = event(100)
    data["message"]["from"]["id"] = 999
    run(config, API(config, [[data]]), monkeypatch, "poll\nstop\n")
    restarted = API(config, [[data], []])
    run(config, restarted, monkeypatch)
    assert len(dispositions(config)) == 1
    # A later new random ID can be lower than historical IDs, on fresh startup.
    restarted = API(config, [[event(1)], []])
    run(config, restarted, monkeypatch)
    assert "offset" not in [p for m, p in restarted.calls if m == "getUpdates"][0]
    assert set(dispositions(config)) == {1, 100}


def test_only_bounded_receive_api(monkeypatch: pytest.MonkeyPatch) -> None:
    api = op.BotAPI("opaque-synthetic-secret")
    calls = []

    def request(*args: Any) -> bytes:
        calls.append(args)
        return b"ok"

    monkeypatch.setattr(api, "_request", request)
    assert (
        api.call("getUpdates", {"offset": "2", "timeout": "0", "limit": "100"}) == b"ok"
    )
    for method, parameters in [
        ("sendMessage", {}),
        ("setWebhook", {}),
        ("getUpdates", {"offset": "-1"}),
        ("getUpdates", {"allowed_updates": "[]"}),
    ]:
        with pytest.raises(op.TelegramHold):
            api.call(method, parameters)
    assert len(calls) == 1


@pytest.mark.parametrize("valid", [True, False])
def test_masked_per_run_input_no_environment(
    config: op.Config, monkeypatch: pytest.MonkeyPatch, valid: bool
) -> None:
    import tkinter as tk
    from tkinter import simpledialog

    class Root:
        def withdraw(self) -> None:
            pass

        def destroy(self) -> None:
            pass

        def bind_all(self, *args: Any, **kwargs: Any) -> None:
            pass

    dummy = str(config.bot_id) + ":" + "x" * 20

    def ask(*args: Any, **kwargs: Any) -> str | None:
        assert kwargs["show"] == "*"
        return dummy if valid else None

    monkeypatch.setattr(tk, "Tk", Root)
    monkeypatch.setattr(simpledialog, "askstring", ask)
    if valid:
        assert op.hidden_token(config) == dummy
    else:
        with pytest.raises(op.TelegramHold):
            op.hidden_token(config)


def test_main_suppresses_unknown_exception(
    config: op.Config,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(op.sys, "argv", ["wu13"])
    assert op.main() == 2
    assert "HOLD" in capsys.readouterr().out
    monkeypatch.setattr(op.sys, "argv", ["wu13", str(config.path)])
    monkeypatch.setattr(op.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(op.sys.stdout, "isatty", lambda: True)

    def fail(_: op.Config) -> None:
        raise RuntimeError("opaque-secret-in-URL")

    monkeypatch.setattr(op, "run", fail)
    assert op.main() == 2
    assert capsys.readouterr().out == "WU13 HOLD: local operator inspection required\n"
    monkeypatch.setattr(op, "run", lambda _: None)
    assert op.main() == 0


def test_main_denies_noninteractive_before_profile_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(op.sys, "argv", ["wu13", "unused-profile"])
    monkeypatch.setattr(op.sys, "stdin", io.StringIO())
    monkeypatch.setattr(op.Config, "read", lambda _: pytest.fail("profile read"))
    assert op.main() == 2
