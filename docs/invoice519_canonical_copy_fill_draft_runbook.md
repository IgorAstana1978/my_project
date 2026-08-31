# Invoice 519 canonical copy-and-fill draft generator

## Scope

`scripts/generate_invoice519_canonical_copy_fill_draft.py` is a case-scoped,
copy-first generator for one local DRAFT Invoice 519 workbook. It never rebuilds
the workbook, recalculates prices, creates PDF, sends a client document, or
authorizes procurement, reserve, prepayment, production, or downstream work.

The generator may be invoked only after a new exact Human Approval for the real
local XLSX generation. Merely passing tests or validating the input artifacts is
not that approval.

## Exact authoritative inputs

- commercial pricing ledger:
  `C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-INVOICE519-COMMERCIAL-PRICING-LEDGER-20260828-001\invoice519-commercial-pricing-ledger-v0.1.json`
  with SHA-256
  `3391f456ff9a01eed59b455549127a73e46aa97b0f4607c291759b5753959fdc`;
- YAUO enclosure Human Decision:
  `C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-INVOICE519-YAUO-ENCLOSURE-HUMAN-DECISION-20260831-001\invoice519-yauo-enclosure-human-decision-v0.1.json`
  with SHA-256
  `214a9114c5b676f3754f3220cfe5b3488d9c4ce75325f98072b7e8e9a5f29717`;
- canonical template:
  `C:\Users\IgorN\Downloads\2026.06.22_519_ТОО «Sensata Industrial».xlsx`
  with SHA-256
  `17e31d0312f728800d31fd4f125d285edb1114880500d4833261239b87ab58b5`.

The ledger must remain strict-valid, APPLIED, 88/88, and exactly
`19 499 186 KZT`. Its frozen/missing subtotals remain `11 963 792` and
`7 535 394 KZT`; arbitrary allocation and repricing remain false. The YAUO
artifact must remain strict-valid, position 87 / `YAUO9601_3474`, dimensions
only, `450×300×250 mm` to `400×300×250 mm`, and NOT_APPLIED_TO_QUOTE.

## Exact canonical map and allowlist

Worksheet: `Лист1`. The 88 position rows are ledger-bound, unique rows from 17
through 112. The preserved section rows are exactly
`32,39,57,64,79,86,103,110`.

The only permitted cell changes are:

- `H` and `I` on all 88 position rows, copied directly from ledger unit prices
  and position totals;
- `I113` = integer `19499186`;
- `C115` = the same canonical amount-words sentence and VAT term with only the
  approved total words updated;
- `G10` = `Срок изготовления 30–40 рабочих дней`;
- `G111` = `Накладной 400х300х250 металл 1,2мм`, derived only from the exact
  YAUO Human Decision.

This is an exact 180-cell allowlist. Canonical position/description/quantity
cells, all section rows, merged cells, styles, row/column dimensions, drawings,
print settings, page setup, formulas outside the allowlist, and every other
OOXML part must remain byte-identical. Target-cell style ids must also remain
unchanged. The generator writes ledger values, not Excel price formulas.

## Safety and publication semantics

The output filename is exactly
`invoice519-canonical-copy-fill-draft.xlsx`. Its new case directory must not
exist, its owner directory must exist, and the output must be outside Git. The
generator performs strict input path/SHA/contract checks, two input byte rereads,
in-memory OOXML patch planning, staged reopen/CRC/XML/value/style validation,
hard-link no-overwrite publication, final reopen validation, and rollback.

The exact future one-run authorization token is:

`IGOR_INVOICE519_CANONICAL_COPY_FILL_DRAFT_GENERATION_AUTHORIZED`

Do not invoke it during implementation, tests, planning, or commit/push work.
Synthetic test workbooks may exist only under pytest temporary directories.

## Quality gate

Run targeted pytest without the global coverage gate, then one final full
project pytest gate with an external `--basetemp`. On final bytes also run Ruff,
Black `--check`, MyPy, strict parse of all committed JSON schemas, Python 3.13
grammar/compile checks used by the project, `git diff --check`, exact Git scope,
and byte-drift comparison. None of these checks authorizes real XLSX generation.
