# Invoice 519 commercial pricing ledger successor

This runbook covers only the additive 88-position commercial pricing ledger
for project `2024/086`, Invoice 519. It does not authorize a real ledger
publication and does not create or modify a quote, invoice, XLSX, or PDF.

## Contract boundary

The successor contract is:

- schema: `invoice519_commercial_pricing_ledger.v0.1`;
- artifact type: `IMMUTABLE_COMMERCIAL_PRICING_LEDGER_SUCCESSOR`;
- ledger ID: `IGOR-INVOICE519-COMMERCIAL-PRICING-LEDGER-2024-086-001`;
- status: `IGOR_INVOICE519_88_POSITION_PRICING_LEDGER_READY_QUOTE_NOT_GENERATED`;
- authority: `IGOR_DIRECT_HUMAN_APPROVAL`;
- pricing scope: `PRICE_ONLY_88_POSITIONS`;
- application status: `APPLIED`;
- output filename: `invoice519-commercial-pricing-ledger-v0.1.json`.

The approved and applied total is exactly `19,499,186 KZT`. The publisher
does not calculate unit prices, read price workbooks, allocate the total, or
run a quote pipeline. It serializes only the already checked position evidence
and verifies the approved multiplicity grain.

## Authoritative predecessor

The only accepted predecessor is:

```text
C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-INVOICE519-PRICE-APPLICATION-20260828-001\invoice519-price-application-v0.1.json
```

Its exact SHA-256 is:

```text
bd86761261a0560cf29649e081769a4d85dcc175ee4f20fd3186f64bd64bcbb0
```

The predecessor is strictly parsed and validated with the committed price
application schema and validator. Path, SHA, schema, application ID, status,
`PRICE_ONLY`, `APPLIED`, exact `19,499,186 KZT`, reconciliation, seven source
bindings, unchanged technical composition, and the closed safety object must
all match.

## Position evidence

Canonical positions `1..88` reference worksheet `Лист1` rows `17..112`, with
the eight section header rows excluded. The ledger stores canonical quantity,
approved unit price, approved position total, pricing provenance, and a
technical-description reference for every position. It does not copy or alter
technical descriptions.

The frozen 55 values come from the real checked calculator position evidence.
The predecessor subtotal is preserved exactly as `11,963,792 KZT`. The final
technical successor evidence includes four SHU-T2 and four SHU-T1 positions at
the already checked `53,763 KZT` unit grain; these are captured values, not a
new calculation.

The remaining 33 values come from the nine already PASS family checks:
`VSHZH_VRU`, `RSHZH`, `AVR`, `SHCHSP`, `UKRM`, `YARV100`, `VSHCHO`, `RSHCHO`,
and `YAUO9601_3474`. Their exact position totals preserve the predecessor
subtotal `7,535,394 KZT`.

The publisher requires exact unique membership `1..88`, duplicates `0`,
missing `0`, extra `0`, exact family membership, exact `55 + 33 = 88`, and
exact line-total sum `19,499,186 KZT`. Every line requires
`approved_unit_price_kzt * canonical quantity = approved_position_total_kzt`.
This multiplication check validates the already approved grain; it is not a
unit-price calculation.

## Quote-layer exclusions

The approved lead time and canonical document style belong to the future quote
layer and are intentionally absent from this pricing ledger. Quote generation,
invoice generation, publication, client send, procurement, reserve,
prepayment, production, and all other downstream actions remain false.
Technical composition is `UNCHANGED_FROM_PRICE_APPLICATION_PREDECESSOR`.

## Fail-closed publication

The publisher requires the exact predecessor path/SHA pair and a new output
directory outside the Git repository. It rejects collisions and wrong output
filenames before writing. It writes and `fsync`s a private staging file,
strictly rereads it, rechecks predecessor bytes and SHA for TOCTOU, then uses
an exclusive no-overwrite hard link. A post-link failure rolls back only the
new link, staging file, and new empty directory; a foreign replacement is
preserved and reported.

## Future CLI template

The authorization phrase below is only a required operator acknowledgement.
Its presence in code or documentation is not Human Approval for a real run.

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\publish_invoice519_commercial_pricing_ledger.py `
  --price-application `
    "C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-INVOICE519-PRICE-APPLICATION-20260828-001\invoice519-price-application-v0.1.json" `
  --price-application-sha256 `
    "bd86761261a0560cf29649e081769a4d85dcc175ee4f20fd3186f64bd64bcbb0" `
  --output <EXACT_NEW_OUTPUT_JSON_OUTSIDE_GIT> `
  --authorization `
    IGOR_INVOICE519_COMMERCIAL_PRICING_LEDGER_PUBLICATION_AUTHORIZED
```

Do not run this publisher without a new exact output path, collision preflight,
and explicit immutable/no-overwrite publication authorization. A ledger PASS
does not authorize quote/invoice creation, client send, or downstream work.

## Review gate

Use synthetic `tmp_path` inputs only for tests. Run the targeted test, then one
full project pytest gate, Ruff, Black `--check`, MyPy, strict schema parse,
Python compile, `git diff --check`, and exact Git diff/status. Do not publish a
real ledger and do not run any quote/invoice pipeline during code review.
