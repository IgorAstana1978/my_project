"""Background runner for the employee bot (Igor's decision 2026-11-06).

Polls Telegram once a minute without an operator at the terminal. The bot
token lives in Windows Credential Manager (saved once with `save-token`), never
in files, argv or environment. Replies are sent only for Cases that have a
request file in `send_queue` next to the profile; that file is created only
after Igor's explicit "yes" for that Case. A short text in
`notify_queue/<CASE_ID>.txt` (e.g. "draft ready") is sent to that Case's chat
as a plain message, no files. A question in
`ask_queue/<CASE_ID>.<user_id>.txt` goes to that employee's own chat (Igor or
PTO from the profile; Igor's decision 2026-11-07). Everything else is unchanged WU13:
same profile, lock, journal, checks and HOLD behaviour.

Usage:
    pythonw wu13_employee_daemon.py run <profile.json>
    python  wu13_employee_daemon.py save-token <profile.json>
"""

from __future__ import annotations

import ctypes
import json
import re
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

import wu13_employee_telegram as op

POLL_SECONDS = 60
RESTART_SECONDS = 50 * 60  # below WU13's one-hour run limit
RETRY_SECONDS = 300
MAX_FAILURES = 3
QUEUE = "send_queue"
NOTICES = "notify_queue"  # <CASE_ID>.txt: short UTF-8 text for that chat
QUESTIONS = "ask_queue"  # <CASE_ID>.<user_id>.txt: question to that employee
STATUS = "status.json"
LOG = "bot.log"
CASE = re.compile(r"CASE-TELEGRAM-[A-F0-9]{64}")


def target(config: op.Config) -> str:
    return f"wu13/{config.username}/telegram-token"


# --- Windows Credential Manager (generic credential, this user only) ---


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.c_uint32),
        ("Type", ctypes.c_uint32),
        ("TargetName", ctypes.c_wchar_p),
        ("Comment", ctypes.c_wchar_p),
        ("LastWritten", ctypes.c_uint64),
        ("CredentialBlobSize", ctypes.c_uint32),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
        ("Persist", ctypes.c_uint32),
        ("AttributeCount", ctypes.c_uint32),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.c_wchar_p),
        ("UserName", ctypes.c_wchar_p),
    ]


def _advapi() -> Any:
    return ctypes.WinDLL("advapi32", use_last_error=True)  # type: ignore[attr-defined]


def store_token(config: op.Config, token: str) -> None:
    blob = token.encode("ascii")
    buffer = ctypes.create_string_buffer(blob, len(blob))
    credential = _Credential(
        Type=1,  # CRED_TYPE_GENERIC
        TargetName=target(config),
        CredentialBlobSize=len(blob),
        CredentialBlob=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)),
        Persist=2,  # CRED_PERSIST_LOCAL_MACHINE: this Windows user, this PC
        UserName="telegram-bot",
    )
    if not _advapi().CredWriteW(ctypes.byref(credential), 0):
        raise op.TelegramHold("token could not be stored")


def stored_token(config: op.Config) -> str:
    advapi = _advapi()
    pointer = ctypes.POINTER(_Credential)()
    if not advapi.CredReadW(target(config), 1, 0, ctypes.byref(pointer)):
        raise op.TelegramHold("stored token missing")
    try:
        item = pointer.contents
        value = ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize)
    finally:
        advapi.CredFree(pointer)
    token = value.decode("ascii", "replace")
    if not re.fullmatch(rf"{config.bot_id}:[A-Za-z0-9_-]{{20,}}", token):
        raise op.TelegramHold("stored token invalid")
    return token


# --- Background command source ---


def write_status(base: Path, state: str, failures: int = 0) -> None:
    value = {"state": state, "time": datetime.now(UTC).isoformat()}
    value["failures"] = failures  # type: ignore[assignment]
    (base / STATUS).write_text(json.dumps(value) + "\n", encoding="utf-8")


class Feeder:
    """Yields `poll` once a minute, `send CASE` for queued requests, then stop."""

    def __init__(
        self,
        base: Path,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base = base
        self.queue = base / QUEUE
        self.sleep = sleep
        self.clock = clock
        self.started = clock()
        self.first = True
        self.notices: dict[str, str] = {}

    def next_request(self) -> str | None:
        if not self.queue.is_dir():
            return None
        for path in sorted(self.queue.iterdir()):
            if not path.is_file():
                continue
            path.unlink()  # consumed once, whatever the outcome
            if CASE.fullmatch(path.name):
                return path.name
        return None

    def next_notice(self) -> str | None:
        folder = self.base / NOTICES
        if not folder.is_dir():
            return None
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            raw = path.read_bytes()
            path.unlink()  # consumed once, whatever the outcome
            case_id = path.name.removesuffix(".txt")
            if CASE.fullmatch(case_id) and len(raw) <= 4000:
                try:
                    self.notices[case_id] = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    continue
                return case_id
        return None

    def notice(self, case_id: str) -> str | None:
        return self.notices.pop(case_id, None)

    def next_question(self) -> str | None:
        folder = self.base / QUESTIONS
        if not folder.is_dir():
            return None
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            raw = path.read_bytes()
            path.unlink()  # consumed once, whatever the outcome
            key = path.name.removesuffix(".txt")
            match = re.fullmatch(
                r"(CASE-TELEGRAM-[A-F0-9]{64})\.([1-9][0-9]{0,15})", key
            )
            if match and len(raw) <= 4000:
                try:
                    self.notices[key] = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    continue
                return f"ask {match.group(1)} {match.group(2)}"
        return None

    def read(self) -> str:
        if self.clock() - self.started >= RESTART_SECONDS:
            return "stop"
        case_id = self.next_request()
        if case_id:
            return f"send {case_id}"
        case_id = self.next_notice()
        if case_id:
            return f"notify {case_id}"
        command = self.next_question()
        if command:
            return command
        if not self.first:
            self.sleep(POLL_SECONDS)
        self.first = False
        write_status(self.base, "RUNNING")
        return "poll"


class _TimedLog:
    def __init__(self, stream: TextIO) -> None:
        self.stream = stream

    def write(self, text: str) -> int:
        if text.strip():
            stamp = datetime.now(UTC).isoformat(timespec="seconds")
            self.stream.write(f"{stamp} {text.strip()}\n")
        return len(text)

    def flush(self) -> None:
        self.stream.flush()


def serve(
    config: op.Config,
    *,
    token: Callable[[op.Config], str] = stored_token,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    base = config.path.parent
    (base / QUEUE).mkdir(exist_ok=True)
    (base / NOTICES).mkdir(exist_ok=True)
    (base / QUESTIONS).mkdir(exist_ok=True)
    failures = 0
    while True:
        feeder = Feeder(base, sleep, clock)
        try:
            op.run(
                config,
                token=token,
                read=feeder.read,
                confirm=lambda: True,
                notice=feeder.notice,
                question=feeder.notice,
            )
            failures = 0
        except BaseException as error:  # noqa: BLE001 - fixed diagnostics only
            if isinstance(error, KeyboardInterrupt):
                write_status(base, "STOPPED", failures)
                return 0
            failures += 1
            print("WU13 BACKGROUND HOLD: local operator inspection required")
            if failures >= MAX_FAILURES:
                write_status(base, "HOLD", failures)
                return 2
            write_status(base, "RETRY", failures)
            sleep(RETRY_SECONDS)


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in {"run", "save-token"}:
        print(__doc__)
        return 2
    config = op.Config.read(Path(argv[2]))
    if argv[1] == "save-token":
        store_token(config, op.hidden_token(config))
        stored_token(config)
        print("Token saved in Windows Credential Manager.")
        return 0
    log = (config.path.parent / LOG).open("a", encoding="utf-8")
    sys.stdout = sys.stderr = _TimedLog(log)  # type: ignore[assignment]
    return serve(config)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
