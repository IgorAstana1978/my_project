"""Questions to employees and adding PTO engineers (Igor's decision 2026-11-07)."""

import json
from pathlib import Path
from typing import Any

import pytest
import wu13_employee_daemon as bg  # type: ignore[import-not-found]
import wu13_employee_telegram as op  # type: ignore[import-not-found]
from test_wu13_employee_daemon import Clock
from test_wu13_employee_reply import SendAPI, accepted_case, send_config
from test_wu13_employee_telegram import config, dispositions, event, run

__all__ = ["config", "send_config"]


def events(config: op.Config) -> list[str]:
    return [r["event"] for r in op.Journal(config).records]


def test_question_goes_to_that_employee_chat_without_reply(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = accepted_case(send_config, monkeypatch)
    journal = op.Journal(send_config)
    api = SendAPI(send_config, [])
    op.ask(send_config, journal, api, case_id, 123, " Шкаф 500х400х250 пойдёт? ")
    assert api.sent == [(123, None, "TEXT", "Шкаф 500х400х250 пойдёт?".encode())]
    record = op.Journal(send_config).records[-1]
    assert record["event"] == "QUESTION"
    assert record["data"]["case_id"] == case_id and record["data"]["user_id"] == 123


@pytest.mark.parametrize("fault", ["stranger", "unknown_case", "empty", "control"])
def test_question_refused(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    case_id = accepted_case(send_config, monkeypatch)
    if fault == "unknown_case":
        case_id = "CASE-TELEGRAM-" + "E" * 64
    user = 999 if fault == "stranger" else 123
    text = {"empty": "  ", "control": "a\x07b"}.get(fault, "вопрос")
    api = SendAPI(send_config, [])
    op.ask(send_config, op.Journal(send_config), api, case_id, user, text)
    assert api.sent == [] and "QUESTION" not in events(send_config)


def test_question_not_confirmed_holds(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = accepted_case(send_config, monkeypatch)
    api = SendAPI(send_config, [])
    api.wrong_chat = True
    with pytest.raises(op.TelegramHold):
        op.ask(send_config, op.Journal(send_config), api, case_id, 123, "вопрос")
    assert "QUESTION" not in events(send_config)


def test_invalid_question_record() -> None:
    case_id = "CASE-TELEGRAM-" + "A" * 64
    good = {"case_id": case_id, "user_id": 5, "text_sha256": "a" * 64}
    op.Journal.validate("QUESTION", good)
    for bad in ({**good, "user_id": 0}, {**good, "user_id": "5"}, {"case_id": case_id}):
        with pytest.raises(op.TelegramHold):
            op.Journal.validate("QUESTION", bad)


def test_telegram_reply_answer_is_accepted(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = event(7)
    data["message"]["text"] = "Да, 500х400х250 пойдёт"
    data["message"]["reply_to_message"] = {
        "message_id": 6,
        "from": {"id": 77777, "is_bot": True},
        "chat": {"id": 123, "type": "private"},
        "date": 1780000000,
        "text": "Шкаф пойдёт?",
    }
    run(send_config, SendAPI(send_config, [[data]]), monkeypatch, "poll\nstop\n")
    assert dispositions(send_config)[7]["event"] == "ACCEPT"


def add_employee(config: op.Config, pair: tuple[int, int]) -> tuple[op.Config, Path]:
    """Keep the old profile as a copy, write the new one in place."""
    old_path = config.path.with_name("profile.before.json")
    old_path.write_bytes(config.path.read_bytes())
    data = json.loads(config.path.read_bytes())
    data["employees"].append({"user_id": pair[0], "chat_id": pair[1]})
    config.path.write_bytes(op.encode(data))
    return op.Config.read(config.path), old_path


def test_adding_pto_engineer_keeps_old_cases_and_accepts_new_one(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = accepted_case(send_config, monkeypatch)
    new, old_path = add_employee(send_config, (789, 789))
    with pytest.raises(op.TelegramHold):
        op.Journal(new)  # without the journalled change the bot stops
    # the failed open recorded a HOLD under the old configuration; still valid
    op.reconfigure(op.Config.read(old_path), new)
    journal = op.Journal(new)
    assert journal.records[-1]["event"] == "RECONFIGURE"
    assert journal.config == new.digest
    data = event(9)
    data["message"]["chat"]["id"] = data["message"]["from"]["id"] = 789
    api = SendAPI(new, [[data]])
    run(new, api, monkeypatch, "poll\nstop\n")
    assert dispositions(new)[9]["event"] == "ACCEPT"
    op.ask(new, op.Journal(new), api, case_id, 789, "Вопрос ПТО")
    assert api.sent[-1][:2] == (789, None)
    with pytest.raises(op.TelegramHold):
        op.Journal(op.Config.read(old_path))  # old profile no longer runs


@pytest.mark.parametrize("change", ["remove", "bot", "same"])
def test_reconfigure_only_adds_employees(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    accepted_case(send_config, monkeypatch)
    old_path = send_config.path.with_name("profile.before.json")
    old_path.write_bytes(send_config.path.read_bytes())
    data = json.loads(send_config.path.read_bytes())
    if change == "remove":
        data["employees"] = data["employees"][:1]
    elif change == "bot":
        data["employees"].append({"user_id": 789, "chat_id": 789})
        data["bot_id"] = 88888
    send_config.path.write_bytes(op.encode(data))
    before = events(op.Config.read(old_path))
    with pytest.raises(op.TelegramHold):
        op.reconfigure(op.Config.read(old_path), op.Config.read(send_config.path))
    assert events(op.Config.read(old_path)) == before


def test_journal_rejects_unannounced_config_change(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    accepted_case(send_config, monkeypatch)
    path = send_config.receipts / op.AUDIT
    lines = path.read_bytes().splitlines(keepends=True)
    record = json.loads(lines[-1])
    record["config"] = "b" * 64
    path.write_bytes(b"".join(lines[:-1]) + op.line(record))
    with pytest.raises(op.TelegramHold):
        op.Journal(send_config)
    for bad in ({"from": "a" * 64}, {"from": "a" * 64, "to": "a" * 64}):
        with pytest.raises(op.TelegramHold):
            op.Journal.validate("RECONFIGURE", bad)


def test_background_sends_queued_question(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = event(5)
    api = SendAPI(send_config, [[data], [], [], [], []])
    monkeypatch.setattr(op, "BotAPI", lambda _: api)
    clock = Clock()
    base = send_config.path.parent
    state: dict[str, Any] = {}

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        records = dispositions(send_config)
        if 5 in records and "queued" not in state:
            case_id = records[5]["data"]["case_id"]
            folder = base / bg.QUESTIONS
            (folder / f"{case_id}.456.txt").write_text("Размер ок?", encoding="utf-8")
            (folder / f"{case_id}.0.txt").write_text("x", encoding="utf-8")
            (folder / "junk.txt").write_bytes(b"x")
            state["queued"] = case_id
        if len([m for m, _ in api.calls if m == "getUpdates"]) >= 4:
            raise KeyboardInterrupt

    result = bg.serve(
        send_config, token=lambda _: "opaque-synthetic-secret", sleep=sleep, clock=clock
    )
    assert result == 0
    assert api.sent == [(456, None, "TEXT", "Размер ок?".encode())]
    assert events(send_config).count("QUESTION") == 1
    assert list((base / bg.QUESTIONS).iterdir()) == []
