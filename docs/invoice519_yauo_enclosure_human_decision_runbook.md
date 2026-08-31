# Invoice 519 YAUO enclosure Human Decision

This runbook covers only the immutable capture of Igor's already approved
field-level enclosure decision for project `2024/086`, Invoice 519, position
`87`, product identity `YAUO9601_3474`. It does not apply the decision to a
quote and does not create an XLSX or PDF.

## Exact contract

- schema: `invoice519_yauo_enclosure_human_decision.v0.1`;
- artifact type: `IMMUTABLE_HUMAN_DECISION_CAPTURE`;
- decision ID: `IGOR-INVOICE519-YAUO-ENCLOSURE-2024-086-001`;
- status: `IGOR_INVOICE519_YAUO_ENCLOSURE_APPROVED_NOT_APPLIED_TO_QUOTE`;
- authority: `IGOR_DIRECT_HUMAN_APPROVAL`;
- approval scope: `ENCLOSURE_DIMENSIONS_ONLY`;
- quote application status: `NOT_APPLIED`;
- output filename: `invoice519-yauo-enclosure-human-decision-v0.1.json`.

The exact bounded decision is:

```text
invoice position: 87
product identity: YAUO9601_3474
field: enclosure_dimensions
previous canonical value: 450×300×250 mm
approved value: 400×300×250 mm
change scope: POSITION_87_ENCLOSURE_ONLY
```

## Canonical source binding

The only source artifact binding is the canonical Invoice 519 workbook:

```text
C:\Users\IgorN\Downloads\2026.06.22_519_ТОО «Sensata Industrial».xlsx
SHA-256: 17e31d0312f728800d31fd4f125d285edb1114880500d4833261239b87ab58b5
worksheet: Лист1
cell: G111
exact cell value: Накладной 450х300х250 металл 1,2мм
```

The publisher reads OOXML through the existing read-only
`scripts/inspect_excel_template.py` helper. It verifies the exact path, SHA,
worksheet, cell, and cell value. The approved value comes only from Igor's
direct Human Approval; no missing technical-review identity is invented.

## Closed safety boundary

Only `human_decision_recorded` and `technical_decision_recorded` are true.
Quote application/generation/publication, invoice generation/publication,
client send, procurement, reserve, prepayment, production, and downstream
authorization remain false. The publisher imports no quote generator and does
not modify the canonical workbook.

## Immutable publication semantics

The output must be outside Git, use the exact filename, and be inside a new
directory whose owner already exists. Any collision fails before writing. The
publisher writes and `fsync`s a private staging file, strictly rereads it,
rechecks the canonical workbook bytes and SHA for TOCTOU, and publishes through
an exclusive hard link. Post-link validation failure rolls back only the
created link, staging file, and new empty directory.

## Future CLI template

The token below is part of the contract, not authorization to run it. A real
publication requires a separate Igor instruction naming the exact new output
path and confirming immutable/no-overwrite intent.

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\publish_invoice519_yauo_enclosure_human_decision.py `
  --canonical-invoice-519 `
    "C:\Users\IgorN\Downloads\2026.06.22_519_ТОО «Sensata Industrial».xlsx" `
  --canonical-invoice-519-sha256 `
    "17e31d0312f728800d31fd4f125d285edb1114880500d4833261239b87ab58b5" `
  --output <EXACT_NEW_OUTPUT_JSON_OUTSIDE_GIT> `
  --authorization `
    IGOR_INVOICE519_YAUO_ENCLOSURE_HUMAN_DECISION_PUBLICATION_AUTHORIZED
```

Do not run this publisher from a code-review PASS. Quote/XLSX/PDF generation,
client send, Git commit/push, and downstream actions require their own exact
authorization.

## Review gate

Use synthetic `tmp_path` workbooks only for tests. Run the targeted tests, one
full project pytest gate, Ruff, Black `--check`, MyPy, strict schema parse,
Python compile, `git diff --check`, and exact Git diff/status. Do not create a
real Human Decision artifact during implementation review.
