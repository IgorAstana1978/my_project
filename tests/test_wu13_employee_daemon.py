"""Background runner: minute polling, queued sends, restarts and HOLD limits."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import wu13_employee_daemon as bg  # type: ignore[import-not-found]
import wu13_employee_telegram as op  # type: ignore[import-not-found]
from test_wu13_employee_reply import SendAPI, prepare, send_config
from test_wu13_employee_telegram import config, dispositions, event

__all__ = ["config", "send_config"]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def status(config: op.Config) -> dict[str, Any]:
    return dict(json.loads((config.path.parent / bg.STATUS).read_text()))


def test_feeder_polls_each_minute_sends_queue_and_restarts(tmp_path: Path) -> None:
    clock = Clock()
    queue = tmp_path / bg.QUEUE
    queue.mkdir()
    feeder = bg.Feeder(tmp_path, clock.sleep, clock)
    assert feeder.read() == "poll" and clock.sleeps == []
    case_id = "CASE-TELEGRAM-" + "B" * 64
    (queue / case_id).write_bytes(b"")
    (queue / "junk.txt").write_bytes(b"")
    (queue / "folder").mkdir()
    assert feeder.read() == f"send {case_id}"
    assert feeder.read() == "poll" and clock.sleeps == [bg.POLL_SECONDS]
    assert [p.name for p in queue.iterdir()] == ["folder"]
    clock.now = bg.RESTART_SECONDS
    assert feeder.read() == "stop"
    assert status_file(tmp_path)["state"] == "RUNNING"
    assert bg.Feeder(tmp_path / "absent").next_request() is None


def status_file(base: Path) -> dict[str, Any]:
    return dict(json.loads((base / bg.STATUS).read_text()))


def test_background_receives_and_sends_queued_reply(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = event(5)
    data["message"]["chat"]["id"] = data["message"]["from"]["id"] = 456
    api = SendAPI(send_config, [[data], [], [], []])
    monkeypatch.setattr(op, "BotAPI", lambda _: api)
    clock = Clock()
    base = send_config.path.parent
    state: dict[str, Any] = {}

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        records = dispositions(send_config)
        if 5 in records and "queued" not in state:
            case_id = records[5]["data"]["case_id"]
            prepare(send_config, case_id, ["КП.xlsx"])
            (base / bg.QUEUE / case_id).write_bytes(b"")
            state["queued"] = case_id
        if len([m for m, _ in api.calls if m == "getUpdates"]) >= 3:
            raise KeyboardInterrupt

    result = bg.serve(
        send_config, token=lambda _: "opaque-synthetic-secret", sleep=sleep, clock=clock
    )
    assert result == 0
    assert [(c, r, n) for c, r, n, _ in api.sent] == [(456, 5, "КП.xlsx")]
    assert state["queued"] in op.Journal(send_config).replies()
    assert status(send_config)["state"] == "STOPPED"
    events = [r["event"] for r in op.Journal(send_config).records]
    assert events[0] == "STARTUP" and "SENT" in events
    assert op.Journal(send_config).records[0]["data"] == {"reason": "BACKGROUND"}


def test_background_restarts_hourly_then_stops_after_repeated_hold(
    config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = SendAPI(config, [[], [], []])
    monkeypatch.setattr(op, "BotAPI", lambda _: api)
    clock = Clock()
    runs = []
    original = op.run

    def run(*args: Any, **kwargs: Any) -> None:
        runs.append(1)
        if len(runs) == 1:
            clock.now += bg.RESTART_SECONDS  # first run ends with a clean stop
            original(*args, **kwargs)
            return
        raise op.TelegramHold("synthetic")

    monkeypatch.setattr(op, "run", run)
    result = bg.serve(
        config,
        token=lambda _: "opaque-synthetic-secret",
        sleep=clock.sleep,
        clock=clock,
    )
    assert result == 2 and len(runs) == 1 + bg.MAX_FAILURES
    assert clock.sleeps == [bg.RETRY_SECONDS] * (bg.MAX_FAILURES - 1)
    assert status(config) == {**status(config), "state": "HOLD", "failures": 3}


def test_main_usage_and_save_token(
    config: op.Config, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    assert bg.main(["x"]) == 2
    saved: dict[str, str] = {}
    monkeypatch.setattr(op, "hidden_token", lambda _: "123:" + "a" * 20)
    monkeypatch.setattr(bg, "store_token", lambda c, t: saved.update(t=t))
    monkeypatch.setattr(bg, "stored_token", lambda c: saved["t"])
    assert bg.main(["x", "save-token", str(config.path)]) == 0
    assert saved["t"].startswith("123:")
    assert "123:" not in capsys.readouterr().out


def test_main_run_logs_with_time_and_no_secret(
    config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    def serve(c: op.Config) -> int:
        print("WU13 READY")
        return 7

    monkeypatch.setattr(bg, "serve", serve)
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    assert bg.main(["x", "run", str(config.path)]) == 7
    sys.stdout.flush()
    log = (config.path.parent / bg.LOG).read_text(encoding="utf-8")
    assert log.rstrip().endswith("WU13 READY") and log[:4].isdigit()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Credential Manager")
def test_credential_round_trip(
    config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bg, "target", lambda c: "wu13/pytest-synthetic/token")
    token = f"{config.bot_id}:" + "s" * 24
    bg.store_token(config, token)
    try:
        assert bg.stored_token(config) == token
        bg.store_token(config, "999:" + "s" * 24)
        with pytest.raises(op.TelegramHold):
            bg.stored_token(config)
    finally:
        bg._advapi().CredDeleteW("wu13/pytest-synthetic/token", 1, 0)
    with pytest.raises(op.TelegramHold):
        bg.stored_token(config)
