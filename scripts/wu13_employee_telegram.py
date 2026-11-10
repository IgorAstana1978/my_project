"""Operator-started employee intake and operator-confirmed reply to the same chat.

Live execution needs separate Igor authority. Replies (profile v2 only) go solely
to the private chat of the recorded employee request, after `send` + `confirm`
(Igor's decision 2026-11-06).
"""

from __future__ import annotations

import http.client
import json
import os
import re
import secrets
import sys
import time
from collections.abc import Callable
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
    PREVIEW_FIELDS,
    PROJECT_ROOT,
    SOURCE_TYPES,
    TelegramHold,
    TelegramPolicy,
    encode,
    integer,
    largest_photo,
    parse_event,
    receive_event,
    reject_credentials,
    roots,
    safe_path,
    sha,
)

PROFILE = "wu13_employee_operational.v1"
PROFILE_SEND = "wu13_employee_operational.v2"
OUTBOX_SUFFIXES = (".xlsx", ".pdf")
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
    outbox: Path | None = None
    # First profile entry; sees copies of all PTO traffic (Igor 2026-11-07).
    owner: tuple[int, int] | None = None

    @property
    def policy(self) -> TelegramPolicy:
        return TelegramPolicy(self.bot_id, frozenset(c for _, c in self.employees))

    @classmethod
    def read(cls, path: Path) -> Config:
        safe_path(path.absolute())
        raw = path.read_bytes()
        value = load(raw)
        fields = {
            "profile",
            "bot_id",
            "bot_username",
            "employees",
            "receipt_root",
            "case_root",
        }
        if not isinstance(value, dict) or not (
            (value.get("profile") == PROFILE and set(value) == fields)
            or (
                value.get("profile") == PROFILE_SEND
                and set(value) == fields | {"outbox_root"}
            )
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
        outbox = None
        if "outbox_root" in value:
            if not isinstance(value["outbox_root"], str) or not (
                Path(value["outbox_root"]).is_absolute()
            ):
                raise TelegramHold("absolute operational roots required")
            safe_path(Path(value["outbox_root"]).absolute())
            outbox = Path(value["outbox_root"]).resolve()
            others = (receipts, cases, wire.RECEIPTS.resolve(), wire.CASES.resolve())
            if (
                not outbox.is_dir()
                or outbox.is_relative_to(PROJECT_ROOT)
                or any(
                    outbox.is_relative_to(other) or other.is_relative_to(outbox)
                    for other in others
                )
            ):
                raise TelegramHold("separate existing outbox outside Git required")
        if any(
            path.resolve().is_relative_to(root)
            for root in (receipts, cases, *([outbox] if outbox else []))
        ):
            raise TelegramHold("profile must be outside output roots")
        return cls(
            path.absolute(),
            sha(raw),
            bot_id,
            username,
            frozenset(pairs),
            receipts,
            cases,
            outbox,
            pairs[0],
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
        current: str | None = None
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
            current = current or record["config"]
            if record["config"] != current:
                raise TelegramHold("audit configuration inconsistent")
            if record["event"] == "RECONFIGURE":
                if record["data"]["from"] != current:
                    raise TelegramHold("audit configuration inconsistent")
                current = record["data"]["to"]
            self.records.append(record)
            previous = sha(raw)
        self.config = current or config.digest
        if self.config != config.digest:
            self.append("HOLD", {"reason": "CONFIG_MISMATCH"})
            raise TelegramHold("operational configuration mismatch")

    @staticmethod
    def validate(event: str, data: Any) -> None:
        if event in {"STARTUP", "HOLD"}:
            if data not in (
                {"reason": "FOREGROUND"},
                {"reason": "BACKGROUND"},
                {"reason": "CONFIG_MISMATCH"},
                {"reason": "LOCAL_OR_TRANSPORT_HOLD"},
            ):
                raise TelegramHold("invalid audit diagnostic")
            return
        if event in {"SEND_INTENT", "SENT"}:
            # Revision 1 has no "revision" field (original records stay valid).
            if (
                not isinstance(data, dict)
                or set(data) - {"revision"} != {"case_id", "outbox_sha256"}
                or (
                    "revision" in data
                    and (
                        type(data["revision"]) is not int
                        or not 2 <= data["revision"] <= MAX_REVISION
                    )
                )
                or not isinstance(data["case_id"], str)
                or not re.fullmatch(r"CASE-TELEGRAM-[A-F0-9]{64}", data["case_id"])
                or not isinstance(data["outbox_sha256"], str)
                or not re.fullmatch(r"[a-f0-9]{64}", data["outbox_sha256"])
            ):
                raise TelegramHold("invalid audit reply")
            return
        if event == "RECONFIGURE":
            if (
                not isinstance(data, dict)
                or set(data) != {"from", "to"}
                or not all(
                    isinstance(v, str) and re.fullmatch(r"[a-f0-9]{64}", v)
                    for v in data.values()
                )
                or data["from"] == data["to"]
            ):
                raise TelegramHold("invalid audit reconfiguration")
            return
        if event == "COPY":
            if (
                not isinstance(data, dict)
                or set(data) != {"case_id"}
                or not isinstance(data["case_id"], str)
                or not re.fullmatch(r"CASE-TELEGRAM-[A-F0-9]{64}", data["case_id"])
            ):
                raise TelegramHold("invalid audit copy")
            return
        if event == "QUESTION":
            if (
                not isinstance(data, dict)
                or set(data) != {"case_id", "user_id", "text_sha256"}
                or not isinstance(data["case_id"], str)
                or not re.fullmatch(r"CASE-TELEGRAM-[A-F0-9]{64}", data["case_id"])
                or type(data["user_id"]) is not int
                or data["user_id"] <= 0
                or not isinstance(data["text_sha256"], str)
                or not re.fullmatch(r"[a-f0-9]{64}", data["text_sha256"])
            ):
                raise TelegramHold("invalid audit question")
            return
        if event == "NOTICE":
            if (
                not isinstance(data, dict)
                or set(data) != {"case_id", "text_sha256"}
                or not isinstance(data["case_id"], str)
                or not re.fullmatch(r"CASE-TELEGRAM-[A-F0-9]{64}", data["case_id"])
                or not isinstance(data["text_sha256"], str)
                or not re.fullmatch(r"[a-f0-9]{64}", data["text_sha256"])
            ):
                raise TelegramHold("invalid audit notice")
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

    def replies(self) -> dict[str, dict[int, str]]:
        """Case -> {revision: sent outbox digest}; revisions go 1, 2, 3 in order.

        An unfinished intent means the remote outcome is unknown.
        """
        intents: dict[tuple[str, int], str] = {}
        sent: dict[tuple[str, int], str] = {}
        for record in self.records:
            data = record["data"]
            if record["event"] not in {"SEND_INTENT", "SENT"}:
                continue
            key = (data["case_id"], data.get("revision", 1))
            if record["event"] == "SEND_INTENT":
                done = [r for c, r in sent if c == key[0]]
                if (
                    key in intents
                    or len(intents) != len(sent)
                    or key[1] != len(done) + 1
                    or data["outbox_sha256"]
                    in {d for (c, _), d in sent.items() if c == key[0]}
                ):
                    raise TelegramHold("duplicate reply intent")
                intents[key] = data["outbox_sha256"]
            else:
                if intents.get(key) != data["outbox_sha256"] or key in sent:
                    raise TelegramHold("reply audit inconsistent")
                sent[key] = data["outbox_sha256"]
        if intents != sent:
            raise TelegramHold("reply outcome unknown: inspect the Telegram chat")
        result: dict[str, dict[int, str]] = {}
        for (case_id, revision), digest in sent.items():
            result.setdefault(case_id, {})[revision] = digest
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
            p
            for p in folder.iterdir()
            if p.name
            in {
                "source.pdf",
                "source.xlsx",
                "source.jpg",
                "source.png",
                "source.webp",
                "source.dwg",
            }
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
    replies = journal.replies()
    if replies and config.outbox is None:
        raise TelegramHold("reply audit without outbox")
    for case_id, revisions in replies.items():
        for revision, digest in revisions.items():
            if (
                case_id not in names
                or outbox_files(config, case_id, revision)[1] != digest
            ):
                raise TelegramHold("sent reply changed")


MAX_REVISION = 99


def outbox_folder(case_id: str, revision: int) -> str:
    """`<CASE_ID>` for the first reply, `<CASE_ID>.<N>` for changed quotes."""
    return case_id if revision == 1 else f"{case_id}.{revision}"


def outbox_files(
    config: Config, case_id: str, revision: int = 1
) -> tuple[list[Path], str]:
    """Exactly one .xlsx and/or one .pdf prepared by the operator for the Case."""
    if config.outbox is None:
        raise TelegramHold("reply outbox not configured")
    folder = config.outbox / outbox_folder(case_id, revision)
    safe_path(folder)
    if not folder.is_dir():
        raise TelegramHold("reply files missing")
    files = list(folder.iterdir())
    suffixes = [p.suffix.lower() for p in files]
    if (
        not files
        or len(set(suffixes)) != len(suffixes)
        or not set(suffixes) <= set(OUTBOX_SUFFIXES)
    ):
        raise TelegramHold("reply files must be one .xlsx and/or one .pdf")
    files.sort(key=lambda p: OUTBOX_SUFFIXES.index(p.suffix.lower()))
    hashes = {}
    for path in files:
        safe_path(path)
        if (
            not path.is_file()
            or not 0 < path.stat().st_size <= MAX_BYTES
            or not re.fullmatch(r'[^\\/:*?"<>|\x00-\x1f]{1,128}', path.name)
        ):
            raise TelegramHold("unsafe reply file")
        hashes[path.name] = sha(path.read_bytes())
    return files, sha(encode(hashes))


class BotAPI(wire.BotAPI):
    def send_message(self, chat_id: int, reply_to: int | None, text: str) -> bytes:
        """sendMessage only; chat_id comes from the verified Case or profile."""
        parameters = {"chat_id": str(chat_id), "text": text}
        if reply_to is not None:
            parameters["reply_parameters"] = json.dumps(
                {"message_id": reply_to, "allow_sending_without_reply": True}
            )
        return self._request(
            f"/bot{self._secret}/sendMessage", urlencode(parameters).encode("ascii")
        )

    def forward_message(
        self, chat_id: int, from_chat_id: int, message_id: int
    ) -> bytes:
        """forwardMessage only; both chats come from the profile."""
        parameters = {
            "chat_id": str(chat_id),
            "from_chat_id": str(from_chat_id),
            "message_id": str(message_id),
        }
        return self._request(
            f"/bot{self._secret}/forwardMessage",
            urlencode(parameters).encode("ascii"),
        )

    def send_document(
        self, chat_id: int, reply_to: int, name: str, body: bytes
    ) -> bytes:
        """sendDocument only; the caller takes chat_id from the verified Case."""
        boundary = secrets.token_hex(16)
        fields = {
            "chat_id": str(chat_id),
            "reply_parameters": json.dumps(
                {"message_id": reply_to, "allow_sending_without_reply": True}
            ),
        }
        parts = [
            (
                f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{key}"\r\n\r\n{value}\r\n'
            ).encode()
            for key, value in fields.items()
        ]
        parts.append(
            (
                f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="document"; filename="{name}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            + body
            + f"\r\n--{boundary}--\r\n".encode()
        )
        connection = http.client.HTTPSConnection("api.telegram.org", timeout=60)
        try:
            connection.request(
                "POST",
                f"/bot{self._secret}/sendDocument",
                body=b"".join(parts),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            response = connection.getresponse()
            if response.status != 200:
                raise TelegramHold("Telegram HTTP request rejected")
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise TelegramHold("Telegram response too large")
            return raw
        except Exception:
            raise TelegramHold("Telegram transport unavailable or rejected") from None
        finally:
            connection.close()

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
        - PREVIEW_FIELDS
        and all(
            isinstance(value.get(k), str) and 0 < len(value[k]) <= 255
            for k in ("file_id", "file_unique_id", "file_name")
        )
        and type(value.get("file_size")) is int
        and 0 < value["file_size"] <= MAX_BYTES
        and not any(c in value["file_name"] for c in "/\\:\x00")
        and Path(value["file_name"]).suffix.lower() in SOURCE_TYPES
    )


def attachment(message: dict[str, Any]) -> dict[str, Any] | None:
    """The file to download: a document, or the largest size of a photo."""
    if "photo" in message:
        try:
            return largest_photo(message["photo"])
        except TelegramHold:
            return {}
    document = message.get("document")
    return document if document is None or supported_document(document) else {}


UNSUPPORTED_TEXT = (
    "Бот не смог прочитать это сообщение. Принимаю текст, ссылки, фото и файлы "
    "PDF, Excel, JPG, PNG, WEBP и чертежи Автокада DWG (до 20 МБ). Голосовые, "
    "видео и архивы не принимаю — пришлите, пожалуйста, текстом или файлом."
)


def tell_unsupported(config: Config, api: BotAPI, raw: bytes) -> None:
    """Igor 2026-11-09: the sender learns at once; Igor gets the message too."""
    message = load(raw)["message"]
    chat_id, message_id = message["chat"]["id"], message["message_id"]
    confirmed(api.send_message(chat_id, message_id, UNSUPPORTED_TEXT), chat_id)
    if config.owner is None or chat_id == config.owner[1]:
        return
    owner = config.owner[1]
    name = employee_name(config, message["from"]["id"])
    text = f"Бот не принял сообщение от {name} (формат не поддерживается):"
    confirmed(api.send_message(owner, None, text), owner)
    confirmed(api.forward_message(owner, chat_id, message_id), owner)


def process(raw: bytes, config: Config, journal: Journal, api: BotAPI) -> str | None:
    """Journal one update; return the REJECT reason the first time, else None."""
    update = load(raw)
    update_id = integer(update.get("update_id"), zero=True)
    previous = journal.dispositions().get(update_id)
    if previous:
        if previous["data"]["raw_sha256"] != sha(raw):
            raise TelegramHold("redelivery changed")
        return None
    reason = None
    body = None
    if not authorized(update, config):
        reason = "UNAUTHORIZED"
    else:
        message = update["message"]
        detail = "unsupported attachment"
        document = attachment(message)
        if document is not None:
            if document:
                body = download(api, document)
            else:
                reason = "UNSUPPORTED"
        if reason is None:
            try:
                parse_event(
                    raw, body, sha(body) if body is not None else None, config.policy
                )
            except TelegramHold as error:
                reason, detail = "UNSUPPORTED", str(error)
        if reason:
            # Field names and fixed texts only: never values or file contents.
            fields = ",".join(sorted(message))
            inner = message.get("document")
            names = ",".join(sorted(inner)) if isinstance(inner, dict) else "-"
            print(
                f"WU13 REJECT DETAIL: {detail}; fields={fields}; document={names}",
                flush=True,
            )
    if reason:
        journal.append(
            "REJECT", {"update_id": update_id, "raw_sha256": sha(raw), "reason": reason}
        )
        return reason
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
    return None


def reply(
    config: Config,
    journal: Journal,
    api: BotAPI,
    case_id: str,
    confirm: Callable[[], bool],
    mirror: bool = False,
) -> None:
    """Operator-confirmed reply to the private chat the Case came from."""
    if config.outbox is None:
        print("WU13 SEND DISABLED: profile v1 is receive-only", flush=True)
        return
    verify_local(config, journal)
    accepted = {
        r["data"]["case_id"]
        for r in journal.dispositions().values()
        if r["event"] == "ACCEPT"
    }
    if case_id not in accepted:
        print("WU13 SEND REFUSED: unknown Case", flush=True)
        return
    # Igor 2026-11-06: a changed quote may be sent again as the next
    # revision, from its own folder `<CASE_ID>.<N>`, with the same confirmation.
    previous = journal.replies().get(case_id, {})
    revision = len(previous) + 1
    if revision > MAX_REVISION:
        print("WU13 SEND REFUSED: too many revisions", flush=True)
        return
    try:
        files, digest = outbox_files(config, case_id, revision)
    except TelegramHold:
        if previous:
            print(
                f"WU13 SEND REFUSED: already sent; a changed quote goes to "
                f"outbox folder <CASE_ID>.{revision}",
                flush=True,
            )
        else:
            print(
                "WU13 SEND REFUSED: outbox needs one .xlsx and/or one .pdf",
                flush=True,
            )
        return
    if digest in previous.values():
        print("WU13 SEND REFUSED: files equal an earlier sent revision", flush=True)
        return
    update = load((config.receipts / case_id / "update.json").read_bytes())
    chat_id = update["message"]["chat"]["id"]
    message_id = integer(update["message"]["message_id"])
    kinds = "+".join(p.suffix.lower()[1:] for p in files)
    print(
        f"WU13 SEND READY: revision {revision}, {kinds} to the request chat; "
        "type confirm",
        flush=True,
    )
    if not confirm():
        print("WU13 SEND CANCELLED", flush=True)
        return
    # Re-check identity and files after the operator's pause.
    verify_local(config, journal)
    if outbox_files(config, case_id, revision)[1] != digest:
        raise TelegramHold("reply files changed before confirm")
    record: dict[str, Any] = {"case_id": case_id, "outbox_sha256": digest}
    if revision > 1:
        record["revision"] = revision
    journal.append("SEND_INTENT", record)
    sent_ids = []
    for path in files:
        result = wire.api_result(
            api.send_document(chat_id, message_id, path.name, path.read_bytes())
        )
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("chat"), dict)
            or result["chat"].get("id") != chat_id
            or not isinstance(result.get("document"), dict)
        ):
            raise TelegramHold("reply not confirmed by Telegram")
        if type(result.get("message_id")) is int:
            sent_ids.append(result["message_id"])
    journal.append("SENT", record)
    if mirror:
        copy_out(config, api, chat_id, "КП отправлено", tuple(sent_ids))
    print("WU13 SENT", flush=True)


MAX_NOTICE_CHARS = 1000


def notify(
    config: Config,
    journal: Journal,
    api: BotAPI,
    case_id: str,
    text: str,
    mirror: bool = False,
) -> None:
    """Short status text to the private chat of an accepted Case (no files)."""
    verify_local(config, journal)
    accepted = {
        r["data"]["case_id"]
        for r in journal.dispositions().values()
        if r["event"] == "ACCEPT"
    }
    if (
        config.outbox is None
        or case_id not in accepted
        or not 0 < len(text.strip()) <= MAX_NOTICE_CHARS
        or re.search(r"[\x00-\x09\x0b-\x1f]", text)
    ):
        print("WU13 NOTICE REFUSED", flush=True)
        return
    update = load((config.receipts / case_id / "update.json").read_bytes())
    chat_id = update["message"]["chat"]["id"]
    message_id = integer(update["message"]["message_id"])
    result = wire.api_result(api.send_message(chat_id, message_id, text.strip()))
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("chat"), dict)
        or result["chat"].get("id") != chat_id
    ):
        raise TelegramHold("notice not confirmed by Telegram")
    journal.append(
        "NOTICE", {"case_id": case_id, "text_sha256": sha(text.strip().encode())}
    )
    if mirror:
        copy_out(config, api, chat_id, text.strip())
    print("WU13 NOTICE SENT", flush=True)


def employee_name(config: Config, user_id: int) -> str:
    """Telegram first/last name from the employee's own accepted messages."""
    for path in sorted(config.receipts.glob("CASE-TELEGRAM-*/update.json")):
        user = load(path.read_bytes())["message"]["from"]
        if user.get("id") == user_id:
            name = " ".join(
                str(user[k]) for k in ("first_name", "last_name") if user.get(k)
            )
            return name or str(user_id)
    return str(user_id)


def confirmed(raw: bytes, chat_id: int) -> dict[str, Any]:
    result = wire.api_result(raw)
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("chat"), dict)
        or result["chat"].get("id") != chat_id
    ):
        raise TelegramHold("copy not confirmed by Telegram")
    return result


def copy_out(
    config: Config,
    api: BotAPI,
    chat_id: int,
    text: str,
    message_ids: tuple[int, ...] = (),
) -> None:
    """Igor sees what the bot sent to a PTO engineer (text and/or files)."""
    if config.owner is None or chat_id == config.owner[1]:
        return
    users = [u for u, c in config.employees if c == chat_id]
    name = employee_name(config, users[0]) if len(users) == 1 else str(chat_id)
    owner = config.owner[1]
    confirmed(api.send_message(owner, None, f"Бот → {name}:\n{text}"), owner)
    for message_id in message_ids:
        confirmed(api.forward_message(owner, chat_id, message_id), owner)


def mirror_incoming(config: Config, journal: Journal, api: BotAPI) -> None:
    """Forward every accepted PTO message to Igor once (journalled COPY)."""
    if config.owner is None:
        return
    copied = {r["data"]["case_id"] for r in journal.records if r["event"] == "COPY"}
    for record in journal.records:
        if record["event"] != "ACCEPT" or record["data"]["case_id"] in copied:
            continue
        case_id = record["data"]["case_id"]
        message = load((config.receipts / case_id / "update.json").read_bytes())[
            "message"
        ]
        if (message["from"]["id"], message["chat"]["id"]) == config.owner:
            continue
        owner = config.owner[1]
        confirmed(
            api.forward_message(owner, message["chat"]["id"], message["message_id"]),
            owner,
        )
        journal.append("COPY", {"case_id": case_id})


def ask(
    config: Config,
    journal: Journal,
    api: BotAPI,
    case_id: str,
    user_id: int,
    text: str,
    mirror: bool = False,
) -> None:
    """Question about an accepted Case to one employee's private chat.

    Igor 2026-11-07: Claude may ask Igor or a PTO engineer listed in the profile.
    The answer arrives as an ordinary message (a new Case) and is data for that
    quote only; it never changes rules, prices, the bot or access.
    """
    verify_local(config, journal)
    accepted = {
        r["data"]["case_id"]
        for r in journal.dispositions().values()
        if r["event"] == "ACCEPT"
    }
    chats = [c for u, c in config.employees if u == user_id]
    if (
        config.outbox is None
        or case_id not in accepted
        or len(chats) != 1
        or not 0 < len(text.strip()) <= MAX_NOTICE_CHARS
        or re.search(r"[\x00-\x09\x0b-\x1f]", text)
    ):
        print("WU13 QUESTION REFUSED", flush=True)
        return
    chat_id = chats[0]
    result = wire.api_result(api.send_message(chat_id, None, text.strip()))
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("chat"), dict)
        or result["chat"].get("id") != chat_id
    ):
        raise TelegramHold("question not confirmed by Telegram")
    journal.append(
        "QUESTION",
        {
            "case_id": case_id,
            "user_id": user_id,
            "text_sha256": sha(text.strip().encode()),
        },
    )
    if mirror:
        copy_out(config, api, chat_id, text.strip())
    print("WU13 QUESTION SENT", flush=True)


def reconfigure(old: Config, new: Config) -> None:
    """Add employees (Igor's explicit "yes", bot stopped): journal the change.

    Everything except the employee list must stay identical, and nobody may
    be removed, so earlier Cases keep verifying.
    """
    same = ("bot_id", "username", "receipts", "cases", "outbox")
    if (
        any(getattr(old, f) != getattr(new, f) for f in same)
        or old.outbox is None
        or not old.employees < new.employees
        or old.owner != new.owner
    ):
        raise TelegramHold("only adding employees is allowed")
    with receiver_lock(old.receipts) as fresh:
        if fresh:
            raise TelegramHold("initialized audit missing or empty")
        journal = Journal(old)
        verify_local(old, journal)
        journal.append("RECONFIGURE", {"from": old.digest, "to": new.digest})
    with receiver_lock(new.receipts):
        verify_local(new, Journal(new))
    print("WU13 RECONFIGURED", flush=True)


def run(
    config: Config,
    *,
    token: Callable[[Config], str] | None = None,
    read: Callable[[], str] | None = None,
    confirm: Callable[[], bool] | None = None,
    notice: Callable[[str], str | None] | None = None,
    question: Callable[[str], str | None] | None = None,
    mirror: bool = False,
) -> None:
    """Foreground by default; the background runner passes its own sources."""
    background = token is not None
    read = read or sys.stdin.readline
    if confirm is None:
        source = read

        def confirm() -> bool:
            return source().strip() == "confirm"

    with receiver_lock(config.receipts) as fresh:
        journal = Journal(config)
        if not fresh and not journal.records:
            raise TelegramHold("initialized audit missing or empty")
        try:
            verify_local(config, journal)
            journal.append(
                "STARTUP", {"reason": "BACKGROUND" if background else "FOREGROUND"}
            )
            started = time.monotonic()
            api = BotAPI((token or hidden_token)(config))
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
                "WU13 READY: local poll / send CASE-ID / stop; "
                "STOP before HUMAN_APPROVAL_1",
                flush=True,
            )
            while True:
                command = read().strip()
                if command in {"", "stop"}:
                    return
                if time.monotonic() - started >= MAX_RUN_SECONDS:
                    raise TelegramHold("foreground coordination expired or invalid")
                target = re.fullmatch(r"send (CASE-TELEGRAM-[A-F0-9]{64})", command)
                if target:
                    reply(config, journal, api, target.group(1), confirm, mirror)
                    continue
                target = re.fullmatch(r"notify (CASE-TELEGRAM-[A-F0-9]{64})", command)
                if target and notice is not None:
                    text = notice(target.group(1))
                    if text is not None:
                        notify(config, journal, api, target.group(1), text, mirror)
                    continue
                target = re.fullmatch(
                    r"ask (CASE-TELEGRAM-[A-F0-9]{64}) ([1-9][0-9]{0,15})", command
                )
                if target and question is not None:
                    text = question(f"{target.group(1)}.{target.group(2)}")
                    if text is not None:
                        ask(
                            config,
                            journal,
                            api,
                            target.group(1),
                            int(target.group(2)),
                            text,
                            mirror,
                        )
                    continue
                if command != "poll":
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
                    if process(raw, config, journal, api) == "UNSUPPORTED" and mirror:
                        tell_unsupported(config, api, raw)
                if mirror:
                    mirror_incoming(config, journal, api)
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
    if len(sys.argv) == 4 and sys.argv[1] == "reconfigure":
        # Run with the bot stopped: old profile copy, then the new profile.
        try:
            reconfigure(Config.read(Path(sys.argv[2])), Config.read(Path(sys.argv[3])))
            return 0
        except BaseException:
            print("WU13 HOLD: reconfiguration refused", flush=True)
            return 2
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
