# WU11 controlled real Telegram TEST pilot

Direct Igor authority: 2026-10-14. Baseline WU10:
`036772418774e6a12e6af0e3c1ac0323eac98022`, CI #220.

Only `@dinva_wu11_test_bot`, discovered using masked local token input and
`getMe`. `DINVA_WU11_TELEGRAM_BOT_TOKEN` exists transiently in this process,
is consumed immediately, and is never passed to children/argv/artifacts.
The exact `DINVA-WU11-ACTIVATION-20261014` message binds exactly one chat.
Unexpected messages/chats, duplicate markers or malformed input HOLD.

2026-10-15 discovery amendment: Igor may physically send exactly one plain
`/start` before the marker, in the same chat, if Telegram activation is needed.
Direct marker without `/start` remains valid. Activation may arrive in the
same poll or an earlier poll; start-only means waiting for the marker, without
creating policy, receipt, Case, extraction input or provenance. Only the marker
establishes the final allowed-chat policy and enters governed text intake.
The exact activation Update is retained only in runtime queue memory so normal
unacknowledged redelivery across text/PDF/XLSX polls can be checked byte-for-byte.
A new/changed start, duplicate identity within one batch, wrong order, foreign
chat, extra message, attached/caption/service payload or non-exact command HOLDs.
The existing limit of three controlled receives per stage is unchanged.
No physical START/marker request or fresh masked bootstrap precedes final
regression, independent review and read-only preflight PASS.

2026-10-15 bounded input diagnosis: Igor confirmed Ctrl+V with Russian layout.
Synthetic physical-key tests on this Windows/Tk reproduce an empty field in RU
and successful paste in EN. A dialog-local physical Ctrl+V binding now invokes
the existing Tk <<Paste>> action once in either layout. Credential validation
is unchanged; no whitespace normalization or alternate secret channel is added.
Diagnosis substitutes Tk's selection getter with dummy data and never reads the
system clipboard. Exactly one fresh live bootstrap is separately authorized
after the proven fix and targeted tests; a failure stops that attempt.

New script: `scripts/wu11_telegram_transport.py`. Run with existing Python.
It opens a local masked-input dialog, verifies getMe, initializes the two authorized
TEST roots only if absent/empty or the exact approved fixture-only cache is present,
then waits for non-secret `poll` commands on
stdin for text, PDF and XLSX. Three bounded receives per stage; no service,
webhook, sends or replies. Do not start a second receiver. Do not put secrets
in commands, prompts, history, logs or screenshots.

Output roots are fixed to the exact approved paths under
`C:\Users\IgorN\Documents\production_ai_cases`:
`WU11-telegram-receipts-test` and `WU11-telegram-cases-test`.
Existing synthetic inbound fixtures are `receipts-root/_smoke-fixtures/wu11-smoke.pdf`
and `wu11-smoke.xlsx`. They contain no commercial/customer data. The operator
uploads one fixture at a time. Original filename/size/getFile identity and
download bytes must match the local approved fixture before governed intake.

Existing-cache initialization is read-only: the Case root must already exist and
be empty, and the receipt root must contain only `_smoke-fixtures`. This cache
must contain exactly the six hash-bound regular files listed in
`APPROVED_FIXTURE_HASHES` and its pre-existing `node_modules` Junction, targeting
exactly `C:\Users\IgorN\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules`.
The PDF SHA-256 is `389c062e9b962c1d1ab62623db31be9b7b8d772c80189f435b8d45ed1650d2ed`;
the XLSX SHA-256 is `48e24bd55d0785a6697a8560c0208cc303cda6b97d7658b5f338550c1acaf39b`.
The authoring Junction is inspected only as a link, never traversed or executed.
All root/source paths retain WU10 safe-path checks. Unknown, missing, changed or
unsafe entries and any previous receipts/Cases HOLD without cleanup, overwrite
or recovery. No fixture/helper is regenerated or executed by this transport.

TLS uses only `api.telegram.org`, system certificate validation, bounded reads,
fixed diagnostics and no HTTP redirects or environment proxies. Authorized API
methods are getMe/getUpdates/getFile plus exact TEST file downloads. getUpdates
has no offset or allowed_updates: no queue acknowledgement or configuration
mutation. A full/foreign queue HOLDs, never automatically discards events.
API errors/bodies/URLs and tracebacks are suppressed.

Update JSON bytes are exact slices of the getUpdates response, not reserialized.
Only WU10 receive_event creates receipt/Case/review artifacts. Each captured
event is replayed locally and every receipt/Case byte hash and mtime must remain
unchanged. Text yields zero items; captions remain outside extraction sources.
Final state is REVIEW_REQUIRED and STOP before HUMAN_APPROVAL_1.

Immutability means exclusive creation and drift checks, not OS WORM or
independent Human authority. Local transport SHA establishes byte traceability;
Telegram supplies no cryptographic source digest. Synthetic tests alone do not
establish live Telegram success. No pricing/quotes/XLSX output/client send or
other production action is authorized. No Git writes are authorized.

Offline checks use existing venv: WU10/WU11 targeted pytest, full pytest with
100% src coverage, Ruff/Black/Mypy for src/tests and the scoped script, and
git diff --check. Preserve native Windows subprocess encoding for full pytest.

Protocol references: [getUpdates](https://core.telegram.org/bots/api#getupdates),
[getMe](https://core.telegram.org/bots/api#getme),
[getFile](https://core.telegram.org/bots/api#getfile).
