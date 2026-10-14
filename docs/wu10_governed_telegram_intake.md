# WU10 — offline governed Telegram intake

Approved scope: direct Igor WU10 instruction, 2026-10-14.
Baseline: `249e7056bcb6474ff4ee4f27df1f0d36ec5db555` (closed WU8).

## Boundaries

Only synthetic/mocked events and local fixtures are authorized. No Telegram
login/API/polling/webhook/getFile/download, real chat, real Case/client artifact,
confirmation, pricing, quote, send, downstream or Git write is authorized.
The module contains no network client, token loader, logger or send operation.
Future real receive/API activation needs separate exact Human Approval.
Future bot credentials must come only from an approved external secret/environment
mechanism, never event JSON, config files, receipts, reports or source code.

## Local interface

`scripts/governed_telegram_intake.py:receive_event` accepts exact already-received
Bot API Update JSON bytes, a non-secret TelegramPolicy, two explicit existing
output roots and optional exact document bytes plus expected SHA-256.
Telegram does not supply a cryptographic attachment SHA: the expected digest
is a local transport snapshot assertion. This is integrity/traceability, not
independent proof of Telegram authenticity or Human Approval.

External non-secret configuration:

- `WU10_TELEGRAM_BOT_ID`: positive numeric bot identity, not a token.
- `WU10_TELEGRAM_ALLOWED_CHATS`: explicit comma-separated integer chat allowlist.

`TelegramPolicy.from_environment()` rejects absent/invalid configuration.
Tests inject synthetic policies; they never load real bot/chat configuration.
Output roots must exist, be disjoint and outside Git. Symlinks, junctions and
reparse ancestors are rejected. Real paths/inputs/write actions require separate
Human Approval before real use. Generated files are never staged by this module.

Supported: one new message Update with text, or one PDF/XLSX document with
optional caption. Edited messages, albums, other media, XLS, ambiguous inputs,
unknown message fields, wrong chat, malformed IDs, missing bytes, changed SHA,
size/MIME/signature mismatch HOLD. Content the existing extractor cannot interpret
may produce its existing manual-review package with unresolved items.
Text-only creates zero engineering items: arbitrary text never becomes a human
decision or inferred composition. Review success does not prove extraction
completeness, composition confirmation or approval authority.

## Receipt, Case and review

The bot-local update_id is the event key. Case ID is
`CASE-TELEGRAM-<full SHA256 of canonical bot_id/update_id identity>`.
Receipt also binds chat_id/message_id. Changed payload/identity for that event
HOLDs. This interface neither acknowledges updates nor advances polling offsets.

Exclusive mkdir claims the event. Exclusive file creation preserves `update.json`,
exact UTF-8 `text.txt`/`caption.txt`, exact original `source.pdf`/`source.xlsx`,
then `receipt.json`. Original filename, file_id, file_unique_id, source hashes
and identity are retained. No source byte normalization occurs. Credential-like
bot tokens and credential fields are rejected before writes, including escaped
nested JSON values. Diagnostics use fixed text and suppress unsafe causes.

Existing `run_case_extraction` calls the existing operator, preliminary validator,
source-bundle verifier and Igor review-card builder. PDF/XLSX use existing
extraction unchanged. Their captions remain in the immutable receipt, outside
engineering/policy inputs. Text-only uses a small operator envelope with zero
items and manual-review status; it never infers engineering content. Existing
default calls retain old behavior. `project_spec_extraction.py` is a full-file
SHA/blob-bound policy owner and remains byte-identical to baseline HEAD. WU10
must not add transport behavior there or rebind replay policy to accommodate it.
Strict JSON/unsafe-path helpers from `governed_case_intake` are reused. Its
versioned intake requiring actual human decision evidence remains unchanged;
no such evidence is fabricated from a Telegram message.

Local `operator-package.json` binds receipt SHA, Case ID, review directory and
manifest/draft/review-card hashes. Result `REVIEW_REQUIRED` has hard STOP before
`HUMAN_APPROVAL_1`, composition_confirmed=false and sending_authorized=false.
It is an operator response payload; nothing is sent to Telegram.

Duplicate verifies exact source/receipt bytes, exact Case inventory, review hashes
and canonical package, then returns the same Case without writes. Concurrent
delivery makes one Case; the loser can HOLD until the package is complete.
Interrupted/failed intake preserves receipt for manual inspection. No automatic
overwrite, cleanup, recovery apply or second Case. Immutability is no-overwrite
plus drift verification, not OS-enforced WORM or an independent trust boundary.
Extra output (including confirmed), tampering or incomplete receipt HOLDs.

## Synthetic checks

Use existing .venv without installations:

On Windows, run the full suite with native default Python process encoding.
Do not force PYTHONIOENCODING/PYTHONUTF8: legacy subprocess tests use native
locale decoding. This does not affect receipt/source bytes, whose UTF-8
encoding is explicit. Remove overrides only from the current shell process:

```powershell
Remove-Item -LiteralPath Env:PYTHONUTF8,Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m pytest tests/test_governed_telegram_intake.py -q
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check src tests
.venv/Scripts/python.exe -m black --check src tests
.venv/Scripts/python.exe -m mypy
git diff --check
```

Also Ruff/Black-check scoped scripts and scoped Mypy with
`--follow-imports=silent` (repository CI scope is src/tests).
Existing coverage gate stays 100% src. WU10 transport coverage is additionally
measured explicitly by targeted tests. No existing gate/approval is relaxed.
Identity semantics follow [official Bot API documentation](https://core.telegram.org/bots/api#update)
and [Document metadata](https://core.telegram.org/bots/api#document).
