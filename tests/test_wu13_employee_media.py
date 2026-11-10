"""Photos, pictures, links and unsupported messages (Igor's decision 2026-11-09)."""

import io
from pathlib import Path
from typing import Any

import pytest
import wu13_employee_telegram as op  # type: ignore[import-not-found]
from test_extract_mixed_source_composition import text_page, write_text_pdf
from test_wu13_employee_reply import SendAPI, send_config
from test_wu13_employee_telegram import config, dispositions, event, run

__all__ = ["config", "send_config"]

JPEG = b"\xff\xd8\xff\xe0" + b"synthetic jpeg body" * 20
PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic png body" * 20
DWG = b"AC1032" + b" synthetic drawing body" * 20
WEBP = b"RIFF\x00\x01\x00\x00WEBPVP8 " + b"synthetic webp body" * 20


def photo_event(update_id: int, body: bytes, api: SendAPI) -> dict[str, Any]:
    data = event(update_id)
    data["message"].pop("text")
    data["message"]["caption"] = "Схема РУСМ 5110-2474"
    data["message"]["media_group_id"] = "123456"
    sizes = []
    for n, size in enumerate((90, 320, 1280)):
        key = f"photo-{update_id}-{n}"
        api.bodies[key] = body[: 40 + n] if size != 1280 else body
        sizes.append(
            {
                "file_id": key,
                "file_unique_id": key,
                "width": size,
                "height": size,
                "file_size": len(api.bodies[key]),
            }
        )
    data["message"]["photo"] = sizes
    return data


def folder(config: op.Config, update_id: int) -> Path:
    case_id: str = dispositions(config)[update_id]["data"]["case_id"]
    return Path(config.receipts) / case_id


def test_photo_is_accepted_as_largest_jpeg(
    config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = SendAPI(config, [])
    data = photo_event(1, JPEG, api)
    api.batches = [[data]]
    run(config, api, monkeypatch, "poll\nstop\n")
    assert dispositions(config)[1]["event"] == "ACCEPT"
    received = folder(config, 1)
    assert (received / "source.jpg").read_bytes() == JPEG
    assert (received / "caption.txt").read_text(encoding="utf-8").startswith("Схема")
    assert (received / "image.txt").exists()
    gets = [p["file_id"] for m, p in api.calls if m == "getFile"]
    assert gets == ["photo-1-2"]  # only the largest size is downloaded
    # restart: the stored photo still verifies
    run(config, SendAPI(config, [[data]]), monkeypatch, "poll\nstop\n")
    op.verify_local(config, op.Journal(config))


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("схема.png", PNG),
        ("фото.JPEG", JPEG),
        ("i.webp", WEBP),
        ("ч.dwg", DWG),
        ("р.pdf", None),
    ],
)
def test_picture_file_is_accepted(
    config: op.Config,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    body: bytes | None,
) -> None:
    if body is None:
        path = tmp_path / "source.pdf"
        write_text_pdf(path, [text_page()])
        body = path.read_bytes()
    api = SendAPI(config, [])
    api.bodies[name] = body
    data = event(2)
    data["message"].pop("text")
    preview = {"file_id": "t", "file_unique_id": "t", "width": 90, "height": 90}
    data["message"]["document"] = {
        "file_id": name,
        "file_unique_id": name,
        "file_name": name,
        "file_size": len(body),
        # Telegram previews are kept as provenance and never downloaded
        "thumbnail": preview,
        "thumb": preview,
    }
    data["message"]["forward_origin"] = {"type": "channel", "date": 1780000000}
    if name.endswith(".pdf"):
        # forwarded files may claim a generic type and start after a preamble
        data["message"]["document"]["mime_type"] = "application/octet-stream"
        body = b"\r\n" + body
        api.bodies[name] = body
        data["message"]["document"]["file_size"] = len(body)
    api.batches = [[data]]
    run(config, api, monkeypatch, "poll\nstop\n")
    assert dispositions(config)[2]["event"] == "ACCEPT"
    assert [p["file_id"] for m, p in api.calls if m == "getFile"] == [name]
    suffix = Path(name.lower()).suffix.replace("jpeg", "jpg")
    assert (folder(config, 2) / f"source{suffix}").read_bytes() == body
    op.verify_local(config, op.Journal(config))


def test_link_and_forwarded_text_are_accepted(
    config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = event(3)
    data["message"]["text"] = "Вот https://example.com/rusm-5110"
    data["message"]["entities"] = [{"type": "url", "offset": 4, "length": 30}]
    data["message"]["link_preview_options"] = {"url": "https://example.com/rusm-5110"}
    data["message"]["forward_origin"] = {"type": "hidden_user", "date": 1780000000}
    data["message"]["forward_date"] = 1780000000
    run(config, SendAPI(config, [[data]]), monkeypatch, "poll\nstop\n")
    assert dispositions(config)[3]["event"] == "ACCEPT"


@pytest.mark.parametrize("fault", ["signature", "photo_and_document", "bad_photo"])
def test_bad_pictures_are_rejected(
    config: op.Config, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    api = SendAPI(config, [])
    data = photo_event(4, b"not a jpeg" * 30 if fault == "signature" else JPEG, api)
    if fault == "photo_and_document":
        data["message"]["document"] = {"file_id": "x", "file_unique_id": "x"}
    if fault == "bad_photo":
        data["message"]["photo"][0]["width"] = "big"
    api.batches = [[data]]
    run(config, api, monkeypatch, "poll\nstop\n")
    assert dispositions(config)[4]["data"]["reason"] == "UNSUPPORTED"
    assert not list(config.cases.iterdir())


def voice(update_id: int, user: int) -> dict[str, Any]:
    data = event(update_id)
    data["message"].pop("text")
    data["message"]["chat"]["id"] = data["message"]["from"]["id"] = user
    data["message"]["voice"] = {"file_id": "v", "file_unique_id": "v", "duration": 3}
    return data


def background_poll(config: op.Config, api: SendAPI, monkeypatch: Any) -> None:
    monkeypatch.setattr(op, "BotAPI", lambda _, api=api: api)
    monkeypatch.setattr(op.sys, "stdin", io.StringIO("poll\nstop\n"))
    op.run(config, token=lambda _: "opaque-synthetic-secret", mirror=True)


def test_unsupported_message_is_answered_and_copied_to_igor_once(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    batch = [voice(7, 456), voice(8, 123), voice(9, 999)]
    api = SendAPI(send_config, [batch])
    background_poll(send_config, api, monkeypatch)
    text = op.UNSUPPORTED_TEXT.encode()
    assert api.sent == [
        (456, 7, "TEXT", text),
        (
            123,
            None,
            "TEXT",
            "Бот не принял сообщение от 456 (формат не " "поддерживается):".encode(),
        ),
        (123, 7, "FORWARD", b"456"),
        (123, 8, "TEXT", text),  # Igor's own message: only the answer
    ]  # a stranger (999) gets nothing
    reasons = {k: v["data"]["reason"] for k, v in dispositions(send_config).items()}
    assert reasons == {7: "UNSUPPORTED", 8: "UNSUPPORTED", 9: "UNAUTHORIZED"}
    again = SendAPI(send_config, [batch])
    background_poll(send_config, again, monkeypatch)
    assert again.sent == []  # redelivery is not answered twice


def test_foreground_does_not_answer_unsupported(
    send_config: op.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = SendAPI(send_config, [[voice(7, 456)]])
    run(send_config, api, monkeypatch, "poll\nstop\n")
    assert api.sent == []
