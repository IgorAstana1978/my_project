# WU13 — employee-only operational adapter

Implementation baseline: `main`, `5ba8166ab053933df285e3633cde094cb925d698`.
Scope: a separate local foreground adapter over unchanged WU10 intake and WU11
HTTPS/raw-Update/duplicate-verification helpers. No commercial or approval flow
is redesigned. Live activation is **not authorized by this implementation**.

## Authority and profile

Before live use Igor must approve the exact operational bot ID/username,
employee `user_id` + private `chat_id` pairs, receipt/Case roots, profile file
and real receive/queue-acknowledgement action. None are supplied or discovered
by this WU. No real profile or operational roots are created here.

The external UTF-8 JSON profile has exactly these fields:

```text
profile: "wu13_employee_operational.v1"
bot_id: approved positive integer
bot_username: approved operational username without @
employees: [{"user_id": approved integer, "chat_id": approved integer}, ...]
receipt_root: approved existing absolute directory outside Git
case_root: approved existing absolute directory outside Git
```

The roots must be separate and non-nested; neither can overlap WU11 TEST roots.
The profile must be outside both output roots. The WU11 TEST bot username is
forbidden. `getMe` must match both configured bot ID and username. Only exact
configured employee pairs with `chat.type == private` and `from.is_bot == false`
can create Cases. Username/display-name matching and discovery are never used
for employee access. Unknown/mismatched identities create only a hashed audit
reject, without downloading attachments or creating Cases.

Changing any profile bytes after first startup causes HOLD, including employee
or root changes. A validated JSON field never creates Human Approval.
Configuration migration/recovery requires a separately approved action;
do not edit/delete the journal to make it pass.

## Foreground operation after separate approval

Use the existing Python to run `scripts/wu13_employee_telegram.py` with exactly
one argument: the approved external profile path, in an interactive terminal
(stdin and stdout must be TTYs). Do not execute this as part
of offline tests or preflight. There is no service, background receiver,
webhook, autostart, automatic reply or automatic polling loop.

## Operator-confirmed reply (Igor's decision 2026-11-06)

Igor allowed the bot to answer approved employees (Igor, PTO) **only in the
same private chat the request came from**, and **only after an explicit
operator command on the computer**. Profile v1 stays receive-only.

Profile `wu13_employee_operational.v2` has the v1 fields plus `outbox_root`:
an existing absolute directory outside Git, separate from and not nested with
the receipt/Case/WU11 roots; the profile must be outside it. The operator puts
the reply files in `outbox_root/<CASE_ID>/`: exactly one `.xlsx` and/or one
`.pdf`, nothing else.

At the prompt the operator types `send <CASE_ID>`. The adapter re-verifies all
local evidence, refuses an unknown Case, an already-sent Case or a wrong outbox
(prints a fixed REFUSED line, nothing is sent), then shows the file kinds and
waits for `confirm`; any other answer cancels. After `confirm` it re-checks the
evidence and that the files did not change, appends `SEND_INTENT`, calls only
`sendDocument` (multipart, fixed host) for each file with `chat_id` taken from
the recorded, still-authorized Case update and `reply_parameters` pointing at
the original message, checks that Telegram confirms the same chat, then appends
`SENT`. Both records hold only the Case ID and a digest of the outbox file
names+hashes. The generic `call()` allow-list is unchanged (no `sendMessage`).

## Background runner (Igor's decision 2026-11-06)

Igor chose automation: "only send the project, Claude works with it".
`scripts/wu13_employee_daemon.py run <profile>` (started hidden with `pythonw`
at Windows logon) drives the same `run()` without a terminal:

- the token is read from Windows Credential Manager (generic credential
  `wu13/<bot_username>/telegram-token`, this Windows user), saved once with
  `save-token <profile>` through the same masked dialog; never in files, argv,
  environment or logs;
- it polls once a minute and ends each run after 50 minutes (below the one-hour
  limit), then restarts with the usual no-offset first poll; STARTUP records
  `BACKGROUND`;
- a reply is sent only for a Case whose empty request file
  `send_queue/<CASE_ID>` (next to the profile, outside all roots) appears; the
  file is consumed once and is the operator confirmation. It is created only
  after Igor's explicit "yes" for that Case (in chat to Claude, or by Igor);
  all `send` checks above still apply;
- any HOLD is logged with a fixed line in `bot.log`; it retries after 5 minutes
  and stops after 3 consecutive failures; `status.json` shows RUNNING / RETRY /
  HOLD / STOPPED. An unfinished send still holds until Igor checks the chat.

A Claude scheduled task reads the new Cases and prepares a draft quote for
Igor; it never creates a `send_queue` file on its own.

Notices (Igor's decision 2026-11-06, "notify both on the phone and in
Telegram"): a UTF-8 text file `notify_queue/<CASE_ID>.txt` (≤ 4000 bytes) is
consumed once and sent with `sendMessage` (fixed method, not via `call()`) as a
reply in that accepted Case's private chat; text 1–1000 characters, no control
characters except newline, profile v2 only. No files, no quote — only status
text such as "draft ready, total, questions". The journal records `NOTICE` with
the Case ID and the text digest. A notice is not Human Approval.

Changed quote (Igor's decision 2026-11-06, "send again if the quote
changed"): after the first reply, `send <CASE_ID>` sends the next revision N
from its own folder `outbox_root/<CASE_ID>.<N>/` (N = 2, 3, … up to 99, same
one `.xlsx` and/or one `.pdf` rule), with the same confirmation (`confirm`, or
the `send_queue` file after Igor's explicit "yes"). Files identical to an
earlier sent revision are refused; a missing next folder is refused. The
journal records revision 2+ as `"revision": N` in `SEND_INTENT`/`SENT`;
revisions must go 1, 2, 3 in order. Every sent revision folder must stay
unchanged.

Questions (Igor's decision 2026-11-07): `ask <CASE_ID> <user_id>` (background:
file `ask_queue/<CASE_ID>.<user_id>.txt`) sends a short text, up to 1000
characters, about an accepted Case to the private chat that the profile pairs
with that employee (Igor or a PTO engineer). Telegram must confirm that chat;
the journal records `QUESTION` with the Case, the user ID and the text digest.
Answers arrive as ordinary messages, including Telegram "Reply" messages
(`reply_to_message` / `quote` are kept as provenance), and become new Cases.
An answer is data for that one quote. It never changes rules, prices, the
formula, the bot or access, and it is never Human Approval. Only Igor decides
those, and only Igor's explicit "yes" sends a quote.

Adding employees (PTO engineers): stop the bot, copy `profile.json` to
`profile.before.json`, add the new `user_id`/`chat_id` pairs to `profile.json`,
then run `python wu13_employee_telegram.py reconfigure profile.before.json
profile.json`. The command refuses any change other than adding employees
(same bot, roots and outbox; nobody removed). It journals
`RECONFIGURE {from, to}` (configuration digests) and re-verifies every earlier
Case under the new profile. Any other profile change still HOLDs.

Each Case revision is answered at most once. A `SEND_INTENT` without `SENT` (crash or
transport failure mid-send) means the remote outcome is unknown: HOLD before
token input until Igor checks the chat and a separately approved recovery is
done. Sent outbox files must stay unchanged; any change is HOLD. Sending is not
Human Approval and does not confirm composition, price or a document release.

A local masked Tk dialog accepts the token once per run, validates its bot-ID
prefix and retains it only in process memory. No argv/environment/file token
input is accepted. WU11's dialog-local RU/EN Ctrl+V binding is reused. Never put
the token in chat, shell history, screenshots, logs or artifacts.

The operator types `poll` for each bounded `getUpdates` call (`timeout=0`,
`limit=100`); `stop`/EOF exits. One process can hold the OS receiver lock for a
root. The retained `_wu13-receiver.lock` sentinel is not removed; the OS releases
its lock on exit/crash. A retained sentinel with missing/empty audit is HOLD,
including when the previous run recorded only rejects and no Cases.
Each foreground run expires after one hour before its
next poll. Restart requires fresh masked token input.

## Queue and restart contract

[Telegram getUpdates](https://core.telegram.org/bots/api#getupdates) confirms
updates as soon as it is called with a higher offset. The adapter omits
`allowed_updates` and negative offsets. Its first poll on every restart has no
offset: it re-reads the earliest unconfirmed input rather than replaying a
persisted high-water mark. This also avoids resuming an old offset across
Telegram's random update-ID reset after inactivity. A bounded foreground run
cannot silently remain polling across that inactivity interval.

Within a batch update IDs must be valid, unique and increasing; gaps are allowed.
Accepted text/PDF/XLSX uses exact raw Update slices and WU10 deterministic Case
identity, extraction and operator package. WU11's local second-delivery check
proves no byte/mtime changes. Captions remain provenance, text requests create
zero engineering items, and all packages stop before `HUMAN_APPROVAL_1`.

All accepted receipt/Case files are flushed with `fsync`; then the ACCEPT record
is appended, flushed and fsynced. It binds update ID, raw SHA and a digest of the
complete receipt/Case file inventory. Unauthorized/unsupported input produces
only a durable REJECT record with update ID, raw SHA and a fixed reason code.
The next operator poll may acknowledge that batch only after the adapter has
rechecked profile bytes, audit bytes, exact root inventory, accepted file hashes
and WU10 duplicate/provenance validation. Previously rejected redelivery must
match its recorded raw SHA. Previously accepted redelivery needs no download.

If a batch fails after a durable prefix, no next ACK is issued. On restart the
prefix is verified and redelivered safely. An interruption during receipt/Case
publication or before its audit record leaves a local inconsistency: HOLD
before token input/API, preserving every output for manual inspection. No
automatic cleanup, overwrite, partial repair, queue skip or retry is provided.
A fully recorded duplicate remains writable only to the append-only run audit;
its receipt/Case bytes and mtimes remain unchanged.

Missing/changed files, extra entries, partial/tampered journal, configuration
drift, download identity/size failure, intake/extraction failure, malformed or
credential-like API data and transport uncertainty all STOP/HOLD. No further
offset is sent for the failing batch. Already issued Telegram ACKs cannot be
undone; a transport failure during an ACK call may leave its remote outcome
unknown, while every input covered by that call was already durable locally.

## Audit and limits

`_wu13-audit.jsonl` is a local canonical hash-linked append-only journal for
startup/config fingerprint, ACCEPT, REJECT and fixed HOLD reason records.
Records include UTC time and sequence. There are no token values, raw payloads,
names, paths, exception strings, URLs or response bodies in the audit/stdout.
Before a valid safe journal/root exists, or if audit writes fail, only the fixed
stdout HOLD is possible; no API ACK is attempted. Existing corrupt evidence is
preserved rather than overwritten to record a new diagnostic.

This is local crash consistency and drift detection, not OS WORM, cryptographic
employee authentication independent of Telegram, or protection from a malicious
same-user administrator rewriting all local evidence. A valid whole-record
tail truncation without remaining Case evidence cannot be detected without
an independent external journal anchor, which this local contract does not add.
`fsync` durability relies
on the OS/filesystem/storage guarantees; power-loss and real Telegram behavior
are not proven by offline tests. Operate with a single approved consumer for the
bot; the local lock cannot exclude an unrelated receiver on another computer.
No extraction, pricing, approval, PDF release or downstream authority is added.

## Offline acceptance

Use existing `.venv`, native Windows subprocess encoding, no installs/network:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_wu13_employee_telegram.py tests/test_governed_telegram_intake.py tests/test_wu11_telegram_transport.py --no-cov
.venv/Scripts/python.exe -m ruff check src tests scripts/wu13_employee_telegram.py
.venv/Scripts/python.exe -m black --check src tests scripts/wu13_employee_telegram.py
.venv/Scripts/python.exe -m mypy
.venv/Scripts/python.exe -m mypy --follow-imports=silent scripts/wu13_employee_telegram.py
.venv/Scripts/python.exe -m pytest -q
git diff --check
```

Full pytest retains the repository's 100% `src` coverage gate. Tests use only
temporary synthetic roots and a substituted API; no real IDs, operational
roots, token entry or Telegram activation is required. Required closure includes
independent read-only review, baseline hash verification, exact three-file scope,
and no stage/commit/push.

Windows verification needs a writable temporary directory outside Git and the
ability to create synthetic junctions for existing WU11 tests. Sandbox denial
of that operation is an environment failure, not an adapter PASS. If Black's
worker pool is unavailable in the sandbox, invoke the same `black --check`
CLI on each Python file sequentially, with the repository configuration.
