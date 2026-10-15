"""Controlled WU11 TEST receive only; no sends, offsets, or persistent service."""

from __future__ import annotations

import http.client
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from governed_case_intake import _pairs
from governed_telegram_intake import (
    MAX_BYTES,
    TelegramHold,
    TelegramPolicy,
    TelegramResult,
    integer,
    parse_event,
    receive_event,
    reject_credentials,
    roots,
    safe_path,
    sha,
)

BOT = "dinva_wu11_test_bot"
MARKER = "DINVA-WU11-ACTIVATION-20261014"
SECRET_ENV = "DINVA_WU11_TELEGRAM_BOT_TOKEN"
RECEIPTS = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\WU11-telegram-receipts-test"
)
CASES = Path(r"C:\Users\IgorN\Documents\production_ai_cases\WU11-telegram-cases-test")
FIXTURES = "_smoke-fixtures"
APPROVED_FIXTURE_HASHES = {
    "wu11-smoke.pdf": (
        "389c062e9b962c1d1ab62623db31be9b7b8d772c80189f435b8d45ed1650d2ed"
    ),
    "wu11-smoke.xlsx": (
        "48e24bd55d0785a6697a8560c0208cc303cda6b97d7658b5f338550c1acaf39b"
    ),
    "create-smoke.mjs": (
        "aef5fa826812a3f337729a429e04847e388299ae6a5ff21ade9be8321917ed4a"
    ),
    "wu11-smoke-pdf.png": (
        "b4a2d99c2c9f68106510e337105e6cec543db7e400ede40deed0acd3811d4e08"
    ),
    "wu11-smoke-xlsx.png": (
        "3eaa9035ab799b3788b2089dda437a21768a6571d9525bf68d5f71035a85b2b0"
    ),
    ".wu11-export.tmp.inspect.ndjson": (
        "1217476ccf68e167d5918e1ca536bebb0e675c1aecd273d0f2a7836aecdaee9a"
    ),
}
AUTHORING_JUNCTION_TARGET = (
    r"C:\Users\IgorN\.cache\codex-runtimes\codex-primary-runtime"
    r"\dependencies\node\node_modules"
)


def _bind_local_paste(root: Any) -> None:
    """Use Tk's normal paste for physical Ctrl+V in this dialog's interpreter."""

    def mapped(event: Any) -> None:
        widget = event.widget
        if widget.winfo_class() != "Entry":
            return

        def paste(key: Any) -> str | None:
            if key.keycode == 0x56:
                widget.event_generate("<<Paste>>")
                return "break"
            return None

        widget.bind("<Control-KeyPress>", paste)

    root.bind_all("<Map>", mapped, add="+")


def hidden_token() -> str:
    """Only local masked input; no terminal fallback, argv, or persisted secret."""
    import tkinter as tk
    from tkinter import simpledialog

    root = tk.Tk()
    root.withdraw()
    _bind_local_paste(root)
    try:
        value = simpledialog.askstring(
            "WU11: local secret input",
            "Token for @dinva_wu11_test_bot (local memory only):",
            show="*",
            parent=root,
        )
        if not value or not re.fullmatch(r"[0-9]{5,}:[A-Za-z0-9_-]{20,}", value):
            raise TelegramHold("hidden secret input cancelled or invalid")
        os.environ[SECRET_ENV] = value
        return os.environ.pop(SECRET_ENV)
    finally:
        os.environ.pop(SECRET_ENV, None)
        root.destroy()


class BotAPI:
    """Fixed TLS host, capped bytes, no proxies/redirects/debug/error bodies."""

    def __init__(self, secret: str) -> None:
        self._secret = secret

    def _request(self, path: str, body: bytes | None = None) -> bytes:
        connection = http.client.HTTPSConnection("api.telegram.org", timeout=15)
        try:
            connection.request(
                "POST" if body is not None else "GET",
                path,
                body=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
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
        if method not in {"getMe", "getUpdates", "getFile"}:
            raise TelegramHold("unapproved Telegram method")
        permitted = {
            "getMe": set(),
            "getUpdates": {"limit", "timeout"},
            "getFile": {"file_id"},
        }
        if set(parameters or {}) - permitted[method]:
            raise TelegramHold("unapproved Telegram parameters")
        return self._request(
            f"/bot{self._secret}/{method}",
            urlencode(parameters or {}).encode("ascii"),
        )

    def download(self, file_path: str) -> bytes:
        if (
            not isinstance(file_path, str)
            or not re.fullmatch(r"[A-Za-z0-9_./-]{1,255}", file_path)
            or any(part in {"", ".", ".."} for part in file_path.split("/"))
        ):
            raise TelegramHold("unsafe Telegram download path")
        return self._request(f"/file/bot{self._secret}/{file_path}")


def api_result(raw: bytes) -> Any:
    try:
        response = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
        reject_credentials(response)
        if not isinstance(response, dict) or set(response) != {"ok", "result"}:
            raise ValueError
        if response["ok"] is not True:
            raise ValueError
        return response["result"]
    except Exception:
        raise TelegramHold("malformed or unsafe Telegram response") from None


def exact_updates(raw: bytes) -> list[bytes]:
    """Extract each exact UTF-8 Update slice, without reserializing Telegram JSON."""
    result = api_result(raw)
    if not isinstance(result, list) or len(result) > 100:
        raise TelegramHold("malformed Telegram update batch")
    try:
        text = raw.decode("utf-8")
        decoder = json.JSONDecoder(object_pairs_hook=_pairs)
        position = text.index("{") + 1
        while True:
            position = skip_space(text, position)
            key, position = decoder.raw_decode(text, position)
            position = skip_space(text, position)
            if text[position] != ":":
                raise ValueError
            position = skip_space(text, position + 1)
            if key == "result":
                if text[position] != "[":
                    raise ValueError
                position += 1
                events = []
                for expected in result:
                    position = skip_space(text, position)
                    start = position
                    event, position = decoder.raw_decode(text, position)
                    if event != expected or not isinstance(event, dict):
                        raise ValueError
                    events.append(text[start:position].encode("utf-8"))
                    position = skip_space(text, position)
                    if text[position] == ",":
                        position += 1
                if text[skip_space(text, position)] != "]":
                    raise ValueError
                return events
            _, position = decoder.raw_decode(text, position)
            position = skip_space(text, position)
            if text[position] != ",":
                raise ValueError
            position += 1
    except Exception:
        raise TelegramHold("malformed exact Telegram update slices") from None


def skip_space(text: str, position: int) -> int:
    while position < len(text) and text[position] in " \r\n\t":
        position += 1
    return position


def identity(raw: bytes) -> tuple[dict[str, Any], int]:
    try:
        update = json.loads(raw, object_pairs_hook=_pairs)
        reject_credentials(update)
        if set(update) != {"update_id", "message"}:
            raise ValueError
        integer(update["update_id"], zero=True)
        message = update["message"]
        integer(message["message_id"])
        integer(message["date"])
        chat_id = integer(message["chat"]["id"], negative=True)
        return update, chat_id
    except Exception:
        raise TelegramHold("malformed or unsupported Telegram identity") from None


def discover(
    events: list[bytes], captured: dict[int, bytes] | None = None
) -> tuple[bytes | None, int]:
    """Bind a marker, retaining at most one activation Update in queue memory."""
    if not events:
        raise TelegramHold("activation marker not received")
    if captured is None:
        captured = {}

    def plain(raw: bytes) -> tuple[dict[str, Any], int]:
        update, chat_id = identity(raw)
        parse_event(raw, None, None, TelegramPolicy(1, frozenset({chat_id})))
        message = update["message"]
        if {"document", "caption", "caption_entities"} & message.keys():
            raise TelegramHold("invalid discovery message")
        if message["text"] == "/start":
            if "entities" in message and message["entities"] != [
                {"offset": 0, "length": 6, "type": "bot_command"}
            ]:
                raise TelegramHold("invalid activation command")
            if "from" in message:
                sender = message["from"]
                if not isinstance(sender, dict) or sender.get("is_bot") is not False:
                    raise TelegramHold("invalid activation sender")
                integer(sender.get("id"))
        elif message["text"] != MARKER:
            raise TelegramHold("unauthorized input during marker discovery")
        return update, chat_id

    if len(captured) > 1:
        raise TelegramHold("unexpected discovery queue state")
    activation = None
    for event_id, raw in captured.items():
        update, chat_id = plain(raw)
        if update["update_id"] != event_id or update["message"]["text"] != "/start":
            raise TelegramHold("unexpected discovery queue state")
        activation = (raw, update, chat_id)
    marker = None
    previous = (-1, 0, 0)
    for raw in events:
        update, chat_id = plain(raw)
        message = update["message"]
        order = (update["update_id"], message["message_id"], message["date"])
        if order[0] <= previous[0] or order[1] <= previous[1] or order[2] < previous[2]:
            raise TelegramHold("duplicate or unordered discovery identity")
        previous = order
        if activation is not None and chat_id != activation[2]:
            raise TelegramHold("unauthorized chat during marker discovery")
        if message["text"] == "/start":
            if marker is not None:
                raise TelegramHold("activation after marker")
            if activation is not None and raw != activation[0]:
                raise TelegramHold("new or changed activation")
            activation = (raw, update, chat_id)
        else:
            if marker is not None:
                raise TelegramHold("ambiguous activation marker")
            if activation is not None:
                start = activation[1]
                if (
                    update["update_id"] <= start["update_id"]
                    or message["message_id"] <= start["message"]["message_id"]
                    or message["date"] < start["message"]["date"]
                ):
                    raise TelegramHold("marker precedes activation identity")
            marker = (raw, chat_id)
    if activation is not None:
        captured[activation[1]["update_id"]] = activation[0]
    if marker is not None:
        return marker
    assert activation is not None
    return None, activation[2]


def _check_fixture_cache(receipt_root: Path) -> None:
    """Recognize only the byte-bound existing cache; never follow its Junction."""
    try:
        if {entry.name for entry in receipt_root.iterdir()} != {FIXTURES}:
            raise TelegramHold("unexpected existing TEST-root contents")
        cache = receipt_root / FIXTURES
        safe_path(cache.absolute())
        if not cache.is_dir() or {entry.name for entry in cache.iterdir()} != {
            *APPROVED_FIXTURE_HASHES,
            "node_modules",
        }:
            raise TelegramHold("unexpected existing TEST fixture inventory")
        for name, expected_hash in APPROVED_FIXTURE_HASHES.items():
            fixture = cache / name
            safe_path(fixture.absolute())
            if not fixture.is_file() or sha(fixture.read_bytes()) != expected_hash:
                raise TelegramHold("approved TEST fixture cache changed")
        junction = cache / "node_modules"
        if (
            not junction.is_junction()
            or os.readlink(junction).removeprefix("\\\\?\\")
            != AUTHORING_JUNCTION_TARGET
        ):
            raise TelegramHold("unexpected TEST authoring Junction")
    except OSError:
        raise TelegramHold("unavailable approved TEST fixture cache") from None


def initialize_roots(receipt_root: Path, case_root: Path) -> None:
    for root in (receipt_root, case_root):
        safe_path(root.absolute())
        if root.exists() and not root.is_dir():
            raise TelegramHold("unexpected existing TEST-root contents")
    if case_root.exists() and any(case_root.iterdir()):
        raise TelegramHold("unexpected existing TEST-root contents")
    if receipt_root.exists() and any(receipt_root.iterdir()):
        _check_fixture_cache(receipt_root)
        roots(receipt_root, case_root)
        return
    for root in (receipt_root, case_root):
        root.mkdir(parents=True, exist_ok=True)
    roots(receipt_root, case_root)


def deliver(
    raw: bytes,
    policy: TelegramPolicy,
    receipt_root: Path,
    case_root: Path,
    body: bytes | None = None,
) -> dict[str, Any]:
    """Existing governed intake twice; independently check no bytes/mtime changed."""

    def receive() -> TelegramResult:
        return receive_event(
            raw_update=raw,
            policy=policy,
            receipt_root=receipt_root,
            case_root=case_root,
            document_bytes=body,
            expected_document_sha256=sha(body) if body is not None else None,
        )

    first = receive()
    if first.status != "REVIEW_REQUIRED" or not first.package or not first.case_id:
        raise TelegramHold("governed intake HOLD; preserve outputs for inspection")
    folders = (first.package.parent, case_root / first.case_id)

    def snapshot() -> dict[str, tuple[str, int]]:
        return {
            str(path): (sha(path.read_bytes()), path.stat().st_mtime_ns)
            for folder in folders
            for path in folder.iterdir()
        }

    before = snapshot()
    duplicate = receive()
    if (
        duplicate.status != "REVIEW_REQUIRED"
        or not duplicate.duplicate
        or duplicate.case_id != first.case_id
        or before != snapshot()
    ):
        raise TelegramHold("duplicate delivery failed no-overwrite verification")
    package = json.loads(first.package.read_bytes(), object_pairs_hook=_pairs)
    if (
        package["stop_before"] != "HUMAN_APPROVAL_1"
        or package["composition_confirmed"] is not False
        or package["sending_authorized"] is not False
    ):
        raise TelegramHold("operator package safety boundary changed")
    update, chat_id = identity(raw)
    draft = json.loads(
        (case_root / first.case_id / "preliminary-composition-draft.json").read_bytes(),
        object_pairs_hook=_pairs,
    )
    manifest = json.loads(
        (case_root / first.case_id / "source-bundle-manifest.txt").read_bytes(),
        object_pairs_hook=_pairs,
    )
    if draft["safety"]["confirmed_by_igor"] is not False:
        raise TelegramHold("preliminary composition approval changed")
    if body is None and draft["items"]:
        raise TelegramHold("text-only produced engineering items")
    if len(manifest["sources"]) != 1:
        raise TelegramHold("caption entered extraction source bundle")
    return {
        "status": "REVIEW_REQUIRED",
        "bot_id": policy.bot_id,
        "chat_id": chat_id,
        "update_id": update["update_id"],
        "message_id": update["message"]["message_id"],
        "update_sha256": sha(raw),
        "source_sha256": sha(body) if body is not None else None,
        "case_id": first.case_id,
        "package": str(first.package),
        "duplicate_no_overwrite": True,
        "engineering_items": len(draft["items"]),
        "caption_provenance_only": body is not None,
        "stop_before": "HUMAN_APPROVAL_1",
    }


def document_bytes(
    api: BotAPI, update: dict[str, Any], fixture: Path, expected: bytes
) -> bytes:
    safe_path(fixture)
    if fixture.read_bytes() != expected:
        raise TelegramHold("approved TEST fixture changed before receive")
    document = update["message"].get("document")
    if (
        not isinstance(document, dict)
        or document.get("file_name") != fixture.name
        or document.get("file_size") != len(expected)
        or not isinstance(document.get("file_id"), str)
        or not document["file_id"]
        or not isinstance(document.get("file_unique_id"), str)
    ):
        raise TelegramHold("input is not the approved TEST fixture")
    info = api_result(api.call("getFile", {"file_id": document["file_id"]}))
    if (
        not isinstance(info, dict)
        or info.get("file_id") != document["file_id"]
        or info.get("file_unique_id") != document["file_unique_id"]
        or info.get("file_size") != len(expected)
    ):
        raise TelegramHold("getFile identity or size changed")
    file_path = info.get("file_path")
    if not isinstance(file_path, str):
        raise TelegramHold("missing Telegram download path")
    body = api.download(file_path)
    if body != expected:
        raise TelegramHold("download differs from approved TEST fixture")
    return body


def live() -> None:
    api = BotAPI(hidden_token())
    bot = api_result(api.call("getMe"))
    if (
        not isinstance(bot, dict)
        or bot.get("username") != BOT
        or bot.get("is_bot") is not True
    ):
        raise TelegramHold("bot identity differs from approved TEST bot")
    bot_id = integer(bot.get("id"))
    initialize_roots(RECEIPTS, CASES)
    print(json.dumps({"stage": "BOOTSTRAP_PASS", "bot_id": bot_id, "bot": BOT}))
    captured: dict[int, bytes] = {}
    approved_bodies: dict[str, bytes] = {}
    policy = None
    for stage in ("text", "pdf", "xlsx"):
        if stage == "pdf":
            for kind in ("pdf", "xlsx"):
                fixture = RECEIPTS / FIXTURES / f"wu11-smoke.{kind}"
                safe_path(fixture)
                approved_bodies[kind] = fixture.read_bytes()
                if not approved_bodies[kind] or len(approved_bodies[kind]) > MAX_BYTES:
                    raise TelegramHold("missing or oversized approved TEST fixture")
                if sha(approved_bodies[kind]) != APPROVED_FIXTURE_HASHES[fixture.name]:
                    raise TelegramHold("approved TEST fixture hash changed")
                print(
                    json.dumps(
                        {"fixture": str(fixture), "sha256": sha(approved_bodies[kind])}
                    ),
                    flush=True,
                )
        print(f"WAIT_FOR_{stage.upper()}", flush=True)
        for _ in range(3):
            # Only non-secret local coordination commands travel via stdin.
            if sys.stdin.readline().strip() != "poll":
                raise TelegramHold("local pilot cancelled")
            events = exact_updates(
                api.call("getUpdates", {"limit": "100", "timeout": "0"})
            )
            if stage == "text":
                if not events:
                    print("MARKER_NOT_YET_RECEIVED", flush=True)
                    continue
                raw, chat_id = discover(events, captured)
                if raw is None:
                    print("MARKER_NOT_YET_RECEIVED", flush=True)
                    continue
                policy = TelegramPolicy(bot_id, frozenset({chat_id}))
                body = None
            else:
                assert policy is not None
                pending = []
                previous = (-1, 0)
                for event in events:
                    update, chat_id = identity(event)
                    if chat_id not in policy.allowed_chat_ids:
                        raise TelegramHold("unauthorized chat in TEST queue")
                    event_id = update["update_id"]
                    message_id = update["message"]["message_id"]
                    if event_id <= previous[0] or message_id <= previous[1]:
                        raise TelegramHold("duplicate or unordered TEST queue identity")
                    previous = (event_id, message_id)
                    if event_id in captured:
                        if captured[event_id] != event:
                            raise TelegramHold("captured redelivery changed")
                    else:
                        if event_id <= max(captured) or message_id <= max(
                            identity(known)[0]["message"]["message_id"]
                            for known in captured.values()
                        ):
                            raise TelegramHold(
                                "new TEST input precedes captured identity"
                            )
                        pending.append(event)
                if not pending:
                    print("FIXTURE_NOT_YET_RECEIVED", flush=True)
                    continue
                if len(pending) != 1:
                    raise TelegramHold("unexpected or ambiguous TEST input")
                raw = pending[0]
                update, _ = identity(raw)
                fixture = RECEIPTS / FIXTURES / f"wu11-smoke.{stage}"
                expected = approved_bodies[stage]
                parse_event(raw, expected, sha(expected), policy)
                body = document_bytes(api, update, fixture, expected)
            assert policy is not None
            evidence = deliver(raw, policy, RECEIPTS, CASES, body)
            captured[evidence["update_id"]] = raw
            print(json.dumps({"stage": stage, **evidence}), flush=True)
            break
        else:
            raise TelegramHold("three controlled receives exhausted")
    print("LIVE_SMOKE_PASS_STOP_BEFORE_HUMAN_APPROVAL_1", flush=True)


def main() -> int:
    try:
        live()
        return 0
    except TelegramHold as error:
        # Only our fixed safe diagnostics; never an HTTP/input exception.
        print(f"WU11 HOLD: {error}", flush=True)
        return 2
    except BaseException:
        # Never display traceback, exception, HTTP URL/body, or untrusted content.
        print("WU11 HOLD: secure bootstrap or controlled pilot failed", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
