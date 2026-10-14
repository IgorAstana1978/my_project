"""Offline Telegram receipt -> preliminary Case review; no API or approval actions."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from extract_mixed_source_composition_case import EXPECTED_FILES, run_case_extraction
from governed_case_intake import _pairs, _unsafe_reparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATTERN = re.compile(rb"[0-9]{5,}:[A-Za-z0-9_-]{20,}")
SCHEMA = "telegram_transport_receipt.v0.1"
MAX_BYTES = 20 * 1024 * 1024


class TelegramHold(ValueError):
    """Safe, fixed diagnostic: payload/credentials must never enter exceptions."""


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encode(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def integer(value: Any, *, negative: bool = False, zero: bool = False) -> int:
    if (
        type(value) is not int
        or abs(value) > 2**52 - 1
        or (not negative and value < 0)
        or (not zero and value == 0)
    ):
        raise TelegramHold("malformed transport identity")
    return value


def reject_credentials(value: Any) -> None:
    """Check decoded JSON too: Unicode escapes cannot hide bot credentials."""
    if isinstance(value, str) and TOKEN_PATTERN.search(value.encode("utf-8")):
        raise TelegramHold("credential-like content is forbidden")
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in {
                "token",
                "bot_token",
                "secret",
                "password",
                "authorization",
            }:
                raise TelegramHold("credential fields are forbidden")
            reject_credentials(key)
            reject_credentials(child)
    elif isinstance(value, list):
        for child in value:
            reject_credentials(child)


@dataclass(frozen=True)
class TelegramPolicy:
    bot_id: int
    allowed_chat_ids: frozenset[int]

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> TelegramPolicy:
        """Read only non-secret configuration; never read or persist a bot token."""
        env = os.environ if environment is None else environment
        try:
            bot = int(env["WU10_TELEGRAM_BOT_ID"])
            chats = frozenset(
                int(item) for item in env["WU10_TELEGRAM_ALLOWED_CHATS"].split(",")
            )
            policy = cls(bot, chats)
            policy.validate()
            return policy
        except KeyError, ValueError:
            raise TelegramHold(
                "external allowed-chat configuration is missing or invalid"
            ) from None

    def validate(self) -> None:
        integer(self.bot_id)
        if (
            not isinstance(self.allowed_chat_ids, frozenset)
            or not self.allowed_chat_ids
        ):
            raise TelegramHold("explicit allowed-chat configuration required")
        for chat in self.allowed_chat_ids:
            integer(chat, negative=True)


@dataclass(frozen=True)
class TelegramResult:
    status: str
    case_id: str | None = None
    package: Path | None = None
    duplicate: bool = False
    blocker: str | None = None


def safe_path(path: Path) -> None:
    """Check lexical ancestors before resolve, including Windows junctions."""
    for entry in (path, *path.parents):
        if os.path.lexists(entry) and _unsafe_reparse(entry):
            raise TelegramHold("unsafe receipt/Case path")


def roots(receipt_root: Path, case_root: Path) -> tuple[Path, Path]:
    for root in (receipt_root, case_root):
        safe_path(root.absolute())
    receipt, case = receipt_root.resolve(), case_root.resolve()
    if (
        not receipt.is_dir()
        or not case.is_dir()
        or receipt.is_relative_to(case)
        or case.is_relative_to(receipt)
        or any(root.is_relative_to(PROJECT_ROOT) for root in (receipt, case))
    ):
        raise TelegramHold("separate existing output roots outside Git are required")
    return receipt, case


def parse_event(
    raw: bytes,
    document_bytes: bytes | None,
    expected_document_sha256: str | None,
    policy: TelegramPolicy,
) -> tuple[str, dict[str, Any], dict[str, bytes]]:
    policy.validate()
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise TelegramHold("missing or oversized transport bytes")
    if TOKEN_PATTERN.search(raw):
        raise TelegramHold("credential-like content is forbidden")
    try:
        update = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except ValueError:
        raise TelegramHold("malformed transport JSON") from None
    reject_credentials(update)
    if not isinstance(update, dict) or set(update) != {"update_id", "message"}:
        raise TelegramHold("only new message updates are supported")
    update_id = integer(update["update_id"], zero=True)
    message = update["message"]
    allowed_fields = {
        "message_id",
        "date",
        "chat",
        "from",
        "text",
        "caption",
        "document",
        "entities",
        "caption_entities",
    }
    if not isinstance(message, dict) or set(message) - allowed_fields:
        raise TelegramHold("unsupported message input")
    message_id = integer(message.get("message_id"))
    integer(message.get("date"))
    chat = message.get("chat")
    if not isinstance(chat, dict):
        raise TelegramHold("malformed transport identity")
    chat_id = integer(chat.get("id"), negative=True)
    if chat_id not in policy.allowed_chat_ids:
        raise TelegramHold("chat is not explicitly allowed")
    files = {"update.json": raw}
    texts: dict[str, Any] = {}
    for field in ("text", "caption"):
        value = message.get(field)
        if field in message:
            if not isinstance(value, str) or not value.strip() or len(value) > 10000:
                raise TelegramHold("invalid text/caption")
            body = value.encode("utf-8")
            files[f"{field}.txt"] = body
            texts[field] = {"file": f"{field}.txt", "sha256": sha(body)}
    document = message.get("document")
    attachment = None
    if document is None:
        if (
            document_bytes is not None
            or expected_document_sha256 is not None
            or "caption" in texts
            or "text" not in texts
        ):
            raise TelegramHold("missing or unexpected input bytes")
    else:
        if (
            "text" in texts
            or not isinstance(document, dict)
            or set(document)
            - {
                "file_id",
                "file_unique_id",
                "file_name",
                "mime_type",
                "file_size",
            }
        ):
            raise TelegramHold("unsupported document input")
        for field in ("file_id", "file_unique_id", "file_name"):
            value = document.get(field)
            if not isinstance(value, str) or not value or len(value) > 255:
                raise TelegramHold("malformed document identity")
        filename = document["file_name"]
        if any(char in filename for char in "/\\:\x00") or filename in {".", ".."}:
            raise TelegramHold("unsafe document filename")
        suffix = Path(filename).suffix.lower()
        mime = {
            ".pdf": "application/pdf",
            ".xlsx": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        }
        if (
            suffix not in mime
            or document.get("mime_type", mime[suffix]) != mime[suffix]
        ):
            raise TelegramHold("unsupported document type")
        if (
            not isinstance(document_bytes, bytes)
            or not document_bytes
            or len(document_bytes) > MAX_BYTES
        ):
            raise TelegramHold("missing or oversized document bytes")
        if TOKEN_PATTERN.search(document_bytes):
            raise TelegramHold("credential-like content is forbidden")
        if expected_document_sha256 != sha(document_bytes):
            raise TelegramHold("document SHA-256 mismatch")
        if "file_size" in document and integer(document["file_size"]) != len(
            document_bytes
        ):
            raise TelegramHold("document size mismatch")
        if (suffix == ".pdf" and not document_bytes.startswith(b"%PDF-")) or (
            suffix == ".xlsx" and not document_bytes.startswith(b"PK\x03\x04")
        ):
            raise TelegramHold("document signature mismatch")
        name = f"source{suffix}"
        files[name] = document_bytes
        attachment = {**document, "file": name, "sha256": sha(document_bytes)}
    identity = {
        "bot_id": policy.bot_id,
        "update_id": update_id,
        "chat_id": chat_id,
        "message_id": message_id,
    }
    # update_id is bot-local; changed chat/message/payload on redelivery HOLDs.
    key = sha(encode({"bot_id": policy.bot_id, "update_id": update_id}))
    case_id = f"CASE-TELEGRAM-{key.upper()}"
    receipt = {
        "schema_version": SCHEMA,
        "case_id": case_id,
        "identity": identity,
        "texts": texts,
        "document": attachment,
        "files": {name: sha(body) for name, body in files.items()},
        "human_approval_1": "REQUIRED",
        "composition_confirmed": False,
    }
    return case_id, receipt, files


def verify_files(folder: Path, expected: dict[str, bytes]) -> None:
    safe_path(folder)
    if not folder.is_dir() or {p.name for p in folder.iterdir()} != set(expected):
        raise TelegramHold("incomplete or conflicting immutable receipt")
    for name, raw in expected.items():
        path = folder / name
        safe_path(path)
        if not path.is_file() or path.read_bytes() != raw:
            raise TelegramHold("immutable source bytes changed")


def verify_case(case: Path, hashes: dict[str, str]) -> None:
    safe_path(case)
    if (
        not case.is_dir()
        or not isinstance(hashes, dict)
        or set(hashes) != EXPECTED_FILES
        or {p.name for p in case.iterdir()} != EXPECTED_FILES
    ):
        raise TelegramHold("Case review inventory changed")
    for name, digest in hashes.items():
        path = case / name
        safe_path(path)
        if not path.is_file() or sha(path.read_bytes()) != digest:
            raise TelegramHold("Case review bytes changed")


def receive_event(
    *,
    raw_update: bytes,
    policy: TelegramPolicy,
    receipt_root: Path,
    case_root: Path,
    document_bytes: bytes | None = None,
    expected_document_sha256: str | None = None,
) -> TelegramResult:
    """Caller supplies already-received bytes. No network, credentials or send.

    Only synthetic execution is currently authorized. Interrupted publication
    remains HOLD for operator inspection, never an automatic write retry.
    """
    case_id = None
    try:
        case_id, receipt, files = parse_event(
            raw_update, document_bytes, expected_document_sha256, policy
        )
        transport, cases = roots(receipt_root, case_root)
        folder, case = transport / case_id, cases / case_id
        safe_path(folder)
        safe_path(case)
        receipt_bytes = encode(receipt)
        sources = {**files, "receipt.json": receipt_bytes}
        package_path = folder / "operator-package.json"
        if os.path.lexists(folder):
            safe_path(package_path)
            if not package_path.is_file():
                raise TelegramHold("incomplete delivery; manual inspection required")
            package_raw = package_path.read_bytes()
            verify_files(folder, {**sources, "operator-package.json": package_raw})
            package = json.loads(package_raw, object_pairs_hook=_pairs)
            verify_case(case, package["review_files"])
            if package_raw != encode(
                operator_package(case_id, receipt_bytes, case, package["review_files"])
            ):
                raise TelegramHold("operator package provenance mismatch")
            return TelegramResult("REVIEW_REQUIRED", case_id, package_path, True)
        if os.path.lexists(case):
            raise TelegramHold("existing Case preserved; overwrite forbidden")
        # Exclusive mkdir is the per-event claim; a racing delivery cannot apply.
        folder.mkdir()
        for name, raw in sources.items():
            with (folder / name).open("xb") as stream:
                stream.write(raw)
        verify_files(folder, sources)
        document = receipt["document"]
        source = folder / document["file"] if document else None
        text = next(
            (
                folder / f"{field}.txt"
                for field in ("text", "caption")
                if field in receipt["texts"]
            ),
            None,
        )
        result = run_case_extraction(
            case_id=case_id,
            canonical_root=cases,
            project_pdf=source if source and source.suffix == ".pdf" else None,
            spec_workbook=source if source and source.suffix == ".xlsx" else None,
            # Captions stay in the receipt, outside engineering/policy inputs.
            request_text=text if source is None else None,
        )
        if result.status != "PASS":
            raise TelegramHold("existing extraction failed; manual inspection required")
        verify_files(folder, sources)
        hashes = {name: sha((case / name).read_bytes()) for name in EXPECTED_FILES}
        verify_case(case, hashes)
        package_raw = encode(operator_package(case_id, receipt_bytes, case, hashes))
        with package_path.open("xb") as stream:
            stream.write(package_raw)
        verify_files(folder, {**sources, "operator-package.json": package_raw})
        return TelegramResult("REVIEW_REQUIRED", case_id, package_path)
    except TelegramHold as error:
        return TelegramResult("HOLD", case_id, blocker=str(error))
    except OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError:
        return TelegramResult(
            "HOLD",
            case_id,
            blocker="receipt/intake malformed; manual inspection required",
        )


def operator_package(
    case_id: str, receipt: bytes, case: Path, hashes: dict[str, str]
) -> dict[str, Any]:
    return {
        "schema_version": "telegram_operator_review.v0.1",
        "case_id": case_id,
        "receipt_sha256": sha(receipt),
        "receipt": "receipt.json",
        "review_directory": str(case),
        "review_files": hashes,
        "status": "REVIEW_REQUIRED",
        "stop_before": "HUMAN_APPROVAL_1",
        "composition_confirmed": False,
        "sending_authorized": False,
    }
