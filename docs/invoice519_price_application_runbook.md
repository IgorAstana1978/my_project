# Invoice 519 price-only application successor

This runbook covers only the additive application contract for Igor's approved
project price for project `2024/086`, Invoice 519. It does not authorize a real
publication by itself and does not create a quote or invoice.

## Contract boundary

The successor contract is:

- schema: `invoice519_price_application.v0.1`;
- artifact type: `IMMUTABLE_PRICE_APPLICATION_SUCCESSOR`;
- application ID: `IGOR-INVOICE519-PRICE-APPLICATION-2024-086-001`;
- status: `IGOR_INVOICE519_PRICE_APPLIED_QUOTE_NOT_GENERATED`;
- authority: `IGOR_DIRECT_HUMAN_APPROVAL`;
- application scope: `PRICE_ONLY`;
- application status: `APPLIED`;
- output filename: `invoice519-price-application-v0.1.json`.

The applied price is exactly `19,499,186 KZT`. The publisher does not calculate
or allocate it. It copies the already checked reconciliation from the immutable
price Human Decision predecessor and requires exact `55 + 33 = 88`, overlap `0`,
uncovered `0`, and the unchanged `11,963,792 + 7,535,394` subtotals.

## Authoritative predecessor

The only accepted predecessor is:

```text
C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-INVOICE519-PRICE-HUMAN-DECISION-20260827-001\invoice519-price-human-decision-v0.1.json
```

Its exact SHA-256 is:

```text
64d78cb69b00eeb89288793c9867be078e9bfc20c590eaa459bd5fed84635e4c
```

The predecessor is strictly parsed and validated with its committed v0.1
schema and validator. Path, SHA, schema, decision ID, status, `PRICE_ONLY`,
`NOT_APPLIED`, approved price, complete reconciliation, seven source bindings,
and the closed predecessor safety object must all match.

## Additive application semantics

The successor preserves all seven predecessor source bindings. Its
`technical_composition` points to the same completed technical input path/SHA
and is `UNCHANGED_FROM_PREDECESSOR`. Both `positions_recalculated` and
`technical_composition_changed` are `false`.

Only these application-layer safety flags are true:

- `human_decision_recorded`;
- `price_approved`;
- `price_application_authorized`;
- `price_applied`.

Quote generation, invoice generation, quote/invoice publication, client send,
lead-time application, procurement, reserve, prepayment, production, and all
other downstream actions remain false. Igor's separately approved lead time
`30–40 рабочих дней` is intentionally not serialized or applied at this layer.

## Fail-closed publication

The publisher requires an exact predecessor path/SHA pair and a new output
directory outside the Git repository. It rejects collisions and wrong output
filenames before writing. After validation it writes and `fsync`s a private
staging file, strictly rereads it, rechecks the predecessor bytes and SHA for
TOCTOU, then publishes by exclusive no-overwrite hard link. Post-link failure
rolls back only the link/staging/new empty directory; a foreign replacement is
preserved and reported.

## Future CLI template

The authorization phrase below is only a required operator acknowledgement.
Its presence in code or documentation is not Human Approval for a real run.

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\publish_invoice519_price_application.py `
  --price-human-decision `
    "C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-INVOICE519-PRICE-HUMAN-DECISION-20260827-001\invoice519-price-human-decision-v0.1.json" `
  --price-human-decision-sha256 `
    "64d78cb69b00eeb89288793c9867be078e9bfc20c590eaa459bd5fed84635e4c" `
  --output <EXACT_NEW_OUTPUT_JSON_OUTSIDE_GIT> `
  --authorization IGOR_INVOICE519_PRICE_APPLICATION_PUBLICATION_AUTHORIZED
```

Do not run the real publisher without a new exact output path, collision
preflight, and explicit immutable/no-overwrite publication instruction. A PASS
does not authorize quote/invoice generation, client send, or downstream work.

## Review gate

Use synthetic `tmp_path` inputs only for tests. Run the targeted test, then one
full project pytest gate, Ruff, Black `--check`, MyPy, schema parse, Python
compile, `git diff --check`, and exact Git diff/status. Do not publish a real
application artifact and do not run any quote/invoice pipeline during code
review.
