"""Operator-started employee intake. Live execution needs separate Igor authority."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import wu11_telegram_transport as wire
from governed_case_intake import _pairs
from governed_telegram_intake import (
    MAX_BYTES,
    TelegramHold,
    TelegramPolicy,
    encode,
    integer,
    parse_event,
    receive_event,
    reject_credentials,
    roots,
    safe_path,
    sha,
)

PROFILE = "wu13_employee_operational.v1"
AUDIT = "_wu13-audit.jsonl"
LOCK = "_wu13-receiver.lock"
MAX_RUN_SECONDS = 3600


def line(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def load(raw: bytes) -> Any:
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    reject_credentials(value)
    return value


@dataclass(frozen=True)
class Config:
    path: Path
    digest: str
    bot_id: int
    username: str
    employees: frozenset[tuple[int, int]]
    receipts: Path
    cases: Path

    @property
    def policy(self) -> TelegramPolicy:
        return TelegramPolicy(self.bot_id, frozenset(c for _, c in self.employees))

    @classmethod
    def read(cls, path: Path) -> Config:
        safe_path(path.absolute())
        raw = path.read_bytes()
        value = load(raw)
        if (
            not isinstance(value, dict)
            or set(value)
            != {
                "profile",
                "bot_id",
                "bot_username",
                "employees",
                "receipt_root",
                "case_root",
            }
            or value["profile"] != PROFILE
        ):
            raise TelegramHold("operational profile required")
        bot_id = integer(value["bot_id"])
        username = value["bot_username"]
        if (
            not isinstance(username, str)
            or not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username)
            or username.casefold() == wire.BOT.casefold()
        ):
            raise TelegramHold("separate operational bot required")
        entries = value["employees"]
        if not isinstance(entries, list) or not entries:
            raise TelegramHold("explicit employee pairs required")
        pairs = []
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"user_id", "chat_id"}:
                raise TelegramHold("explicit employee pairs required")
            pairs.append((integer(entry["user_id"]), integer(entry["chat_id"])))
        if len(set(pairs)) != len(pairs):
            raise TelegramHold("duplicate employee configuration")
        output = []
        for field in ("receipt_root", "case_root"):
            if (
                not isinstance(value[field], str)
                or not Path(value[field]).is_absolute()
            ):
                raise TelegramHold("absolute operational roots required")
            output.append(Path(value[field]))
        receipts, cases = roots(*output)
        for root in (receipts, cases):
            for test in (wire.RECEIPTS.resolve(), wire.CASES.resolve()):
                if root.is_relative_to(test) or test.is_relative_to(root):
                    raise TelegramHold("WU11 roots are forbidden")
        if any(path.resolve().is_relative_to(root) for root in (receipts, cases)):
            raise TelegramHold("profile must be outside output roots")
        return cls(
            path.absolute(),
            sha(raw),
            bot_id,
            username,
            frozenset(pairs),
            receipts,
            cases,
        )

    def unchanged(self) -> None:
        if Config.read(self.path) != self:
            raise TelegramHold("operational configuration changed")


@contextmanager
def receiver_lock(root: Path) -> Any:
    """OS-held lock survives crashes as an unlocked, retained sentinel."""
    path = root / LOCK
    safe_path(path)
    try:
        stream = path.open("x+b")
        fresh = True
    except FileExistsError:
        stream = path.open("r+b")
        fresh = False
    with stream:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            if fresh:
                stream.write(b"0")
                stream.flush()
                os.fsync(stream.fileno())
            elif stream.read() != b"0":
                raise TelegramHold("receiver sentinel changed")
            yield fresh
        finally:
            stream.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


class Journal:
    """Hash-linked local append-only audit; no payload, path or secret values."""

    def __init__(self, config: Config) -> None:
        self.path = config.receipts / AUDIT
        safe_path(self.path)
        self.records: list[dict[str, Any]] = []
        self.raw = self.path.read_bytes() if self.path.exists() else b""
        previous = "0" * 64
        for raw in self.raw.splitlines(keepends=True):
            record = load(raw)
            if (
                not isinstance(record, dict)
                or set(record) != {"seq", "previous", "config", "time", "event", "data"}
                or raw != line(record)
                or record["seq"] != len(self.records) + 1
                or record["previous"] != previous
            ):
                raise TelegramHold("audit chain inconsistent")
            self.validate(record["event"], record["data"])
            if self.records and record["config"] != self.records[0]["config"]:
                raise TelegramHold("audit configuration inconsistent")
            self.records.append(record)
            previous = sha(raw)
        self.config = self.records[0]["config"] if self.records else config.digest
        if self.config != config.digest:
            self.append("HOLD", {"reason": "CONFIG_MISMATCH"})
            raise TelegramHold("operational configuration mismatch")

    @staticmethod
    def validate(event: str, data: Any) -> None:
        if event in {"STARTUP", "HOLD"}:
            if data not in (
                {"reason": "FOREGROUND"},
                {"reason": "CONFIG_MISMATCH"},
                {"reason": "LOCAL_OR_TRANSPORT_HOLD"},
            ):
                raise TelegramHold("invalid audit diagnostic")
            return
        fields = (
            {"update_id", "raw_sha256", "reason"}
            if event == "REJECT"
            else {"update_id", "raw_sha256", "case_id", "tree_sha256"}
        )
        if (
            event not in {"ACCEPT", "REJECT"}
            or not isinstance(data, dict)
            or set(data) != fields
        ):
            raise TelegramHold("invalid audit disposition")
        integer(data["update_id"], zero=True)
        for name in ("raw_sha256", "tree_sha256"):
            if name in data and (
                not isinstance(data[name], str)
                or not re.fullmatch(r"[a-f0-9]{64}", data[name])
            ):
                raise TelegramHold("invalid audit digest")
        if event == "REJECT" and data["reason"] not in {"UNAUTHORIZED", "UNSUPPORTED"}:
            raise TelegramHold("invalid reject reason")
        if event == "ACCEPT" and (
            not isinstance(data["case_id"], str)
            or not re.fullmatch(r"CASE-TELEGRAM-[A-F0-9]{64}", data["case_id"])
        ):
            raise TelegramHold("invalid audit Case")

    def intact(self) -> None:
        safe_path(self.path)
        if (self.path.read_bytes() if self.path.exists() else b"") != self.raw:
            raise TelegramHold("audit changed during run")

    def append(self, event: str, data: dict[str, Any]) -> None:
        self.validate(event, data)
        self.intact()
        record = {
            "seq": len(self.records) + 1,
            "previous": sha(line(self.records[-1])) if self.records else "0" * 64,
            "config": self.config,
            "time": datetime.now(UTC).isoformat(),
            "event": event,
            "data": data,
        }
        raw = line(record)
        with self.path.open("ab") as stream:
            if stream.write(raw) != len(raw):
                raise TelegramHold("audit write incomplete")
            stream.flush()
            os.fsync(stream.fileno())
        self.raw += raw
        self.records.append(record)
        self.intact()

    def dispositions(self) -> dict[int, dict[str, Any]]:
        result = {}
        for record in self.records:
            if record["event"] in {"ACCEPT", "REJECT"}:
                key = record["data"]["update_id"]
                if key in result:
                    raise TelegramHold("duplicate audit identity")
                result[key] = record
        return result


def authorized(update: dict[str, Any], config: Config) -> bool:
    message = update.get("message")
    if not isinstance(message, dict):
        return False
    chat, user = message.get("chat"), message.get("from")
    return (
        isinstance(chat, dict)
        and isinstance(user, dict)
        and chat.get("type") == "private"
        and user.get("is_bot") is False
        and type(user.get("id")) is int
        and type(chat.get("id")) is int
        and (user["id"], chat["id"]) in config.employees
    )


def tree_hash(config: Config, case_id: str, *, sync: bool = False) -> str:
    hashes = {}
    for label, root in (("receipt", config.receipts), ("case", config.cases)):
        folder = root / case_id
        safe_path(folder)
        for path in sorted(folder.iterdir()):
            safe_path(path)
            if not path.is_file():
                raise TelegramHold("unexpected local entry")
            if sync:
                # Windows _commit/fsync requires a writable descriptor. Opening
                # r+b neither truncates nor changes bytes/mtime; never write here.
                with path.open("r+b") as stream:
                    os.fsync(stream.fileno())
            hashes[f"{label}/{path.name}"] = sha(path.read_bytes())
    return sha(encode(hashes))


def verify_local(config: Config, journal: Journal) -> None:
    config.unchanged()
    journal.intact()
    accepted = [
        r["data"] for r in journal.dispositions().values() if r["event"] == "ACCEPT"
    ]
    names = {r["case_id"] for r in accepted}
    if {p.name for p in config.receipts.iterdir()} - {LOCK, AUDIT} != names or {
        p.name for p in config.cases.iterdir()
    } != names:
        raise TelegramHold("unrecorded or incomplete local delivery")
    for data in accepted:
        if tree_hash(config, data["case_id"]) != data["tree_sha256"]:
            raise TelegramHold("local delivery changed")
        folder = config.receipts / data["case_id"]
        raw = (folder / "update.json").read_bytes()
        update = load(raw)
        if (
            sha(raw) != data["raw_sha256"]
            or not authorized(update, config)
            or update["update_id"] != data["update_id"]
        ):
            raise TelegramHold("local identity changed")
        documents = [
            p for p in folder.iterdir() if p.name in {"source.pdf", "source.xlsx"}
        ]
        body = documents[0].read_bytes() if documents else None
        result = receive_event(
            raw_update=raw,
            policy=config.policy,
            receipt_root=config.receipts,
            case_root=config.cases,
            document_bytes=body,
            expected_document_sha256=sha(body) if body else None,
        )
        if (
            result.status != "REVIEW_REQUIRED"
            or not result.duplicate
            or result.case_id != data["case_id"]
        ):
            raise TelegramHold("duplicate verification failed")


class BotAPI(wire.BotAPI):
    def call(self, method: str, parameters: dict[str, str] | None = None) -> bytes:
        parameters = parameters or {}
        permitted = {
            "getMe": set(),
            "getUpdates": {"limit", "timeout", "offset"},
            "getFile": {"file_id"},
        }
        if method not in permitted or set(parameters) - permitted[method]:
            raise TelegramHold("unapproved operational API method or parameters")
        if "offset" in parameters and not re.fullmatch(r"[0-9]+", parameters["offset"]):
            raise TelegramHold("invalid queue acknowledgement")
        return self._request(
            f"/bot{self._secret}/{method}", urlencode(parameters).encode("ascii")
        )


def hidden_token(config: Config) -> str:
    import tkinter as tk
    from tkinter import simpledialog

    root = tk.Tk()
    root.withdraw()
    wire._bind_local_paste(root)
    try:
        value = simpledialog.askstring(
            "WU13: local secret input",
            "Operational bot token (memory only):",
            show="*",
            parent=root,
        )
        if not value or not re.fullmatch(
            rf"{config.bot_id}:[A-Za-z0-9_-]{{20,}}", value
        ):
            raise TelegramHold("masked operational token invalid or cancelled")
        return value
    finally:
        root.destroy()


def download(api: BotAPI, document: dict[str, Any]) -> bytes:
    info = wire.api_result(api.call("getFile", {"file_id": document["file_id"]}))
    if (
        not isinstance(info, dict)
        or any(
            info.get(key) != document[key]
            for key in ("file_id", "file_unique_id", "file_size")
        )
        or not isinstance(info.get("file_path"), str)
    ):
        raise TelegramHold("download identity mismatch")
    body = api.download(info["file_path"])
    if len(body) != document["file_size"]:
        raise TelegramHold("download size mismatch")
    return body


def supported_document(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and not set(value)
        - {"file_id", "file_unique_id", "file_name", "mime_type", "file_size"}
        and all(
            isinstance(value.get(k), str) and 0 < len(value[k]) <= 255
            for k in ("file_id", "file_unique_id", "file_name")
        )
        and type(value.get("file_size")) is int
        and 0 < value["file_size"] <= MAX_BYTES
        and not any(c in value["file_name"] for c in "/\\:\x00")
        and Path(value["file_name"]).suffix.lower() in {".pdf", ".xlsx"}
    )


def process(raw: bytes, config: Config, journal: Journal, api: BotAPI) -> None:
    update = load(raw)
    update_id = integer(update.get("update_id"), zero=True)
    previous = journal.dispositions().get(update_id)
    if previous:
        if previous["data"]["raw_sha256"] != sha(raw):
            raise TelegramHold("redelivery changed")
        return
    reason = None
    body = None
    if not authorized(update, config):
        reason = "UNAUTHORIZED"
    else:
        document = update["message"].get("document")
        if document is not None:
            if supported_document(document):
                body = download(api, document)
            else:
                reason = "UNSUPPORTED"
        if reason is None:
            try:
                parse_event(
                    raw, body, sha(body) if body is not None else None, config.policy
                )
            except TelegramHold:
                reason = "UNSUPPORTED"
    if reason:
        journal.append(
            "REJECT", {"update_id": update_id, "raw_sha256": sha(raw), "reason": reason}
        )
        return
    evidence = wire.deliver(raw, config.policy, config.receipts, config.cases, body)
    digest = tree_hash(config, evidence["case_id"], sync=True)
    journal.append(
        "ACCEPT",
        {
            "update_id": update_id,
            "raw_sha256": sha(raw),
            "case_id": evidence["case_id"],
            "tree_sha256": digest,
        },
    )


def run(config: Config) -> None:
    with receiver_lock(config.receipts) as fresh:
        journal = Journal(config)
        if not fresh and not journal.records:
            raise TelegramHold("initialized audit missing or empty")
        try:
            verify_local(config, journal)
            journal.append("STARTUP", {"reason": "FOREGROUND"})
            started = time.monotonic()
            api = BotAPI(hidden_token(config))
            bot = wire.api_result(api.call("getMe"))
            if (
                not isinstance(bot, dict)
                or bot.get("is_bot") is not True
                or type(bot.get("id")) is not int
                or bot["id"] != config.bot_id
                or bot.get("username") != config.username
            ):
                raise TelegramHold("operational bot identity mismatch")
            # Never resume with a persisted offset: Telegram can randomize IDs
            # after a week of inactivity. Re-read the earliest unconfirmed batch.
            offset = None
            print(
                "WU13 READY: local poll / stop; STOP before HUMAN_APPROVAL_1",
                flush=True,
            )
            while True:
                command = sys.stdin.readline().strip()
                if command in {"", "stop"}:
                    return
                if command != "poll" or time.monotonic() - started >= MAX_RUN_SECONDS:
                    raise TelegramHold("foreground coordination expired or invalid")
                verify_local(config, journal)
                parameters = {"limit": "100", "timeout": "0"}
                if offset is not None:
                    parameters["offset"] = str(offset)
                events = wire.exact_updates(api.call("getUpdates", parameters))
                ids = [integer(load(raw).get("update_id"), zero=True) for raw in events]
                if ids != sorted(set(ids)) or (
                    offset is not None and ids and ids[0] < offset
                ):
                    raise TelegramHold("unordered or regressing queue")
                for raw in events:
                    process(raw, config, journal, api)
                verify_local(config, journal)
                if ids:
                    offset = ids[-1] + 1
                print(
                    "WU13 LOCAL_DISPOSITIONS_DURABLE; STOP before HUMAN_APPROVAL_1",
                    flush=True,
                )
        except BaseException:
            journal.append("HOLD", {"reason": "LOCAL_OR_TRANSPORT_HOLD"})
            raise


def main() -> int:
    try:
        if len(sys.argv) != 2 or not sys.stdin.isatty() or not sys.stdout.isatty():
            raise TelegramHold("exact approved profile path required")
        run(Config.read(Path(sys.argv[1])))
        return 0
    except BaseException:
        # Never print input, token, URL, API body, exception text or traceback.
        print("WU13 HOLD: local operator inspection required", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
