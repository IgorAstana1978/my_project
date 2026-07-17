# Phase 2.33 — checked multi-item clientization runbook

## Purpose

`scripts/checked_clientize_quote.py` creates a client-facing multi-item XLSX
candidate from an approved tuned_v4 internal draft. The checked PowerShell
entry point is `scripts/run_checked_clientization.ps1`.

The transformer does not calculate prices, create PDFs, send files, call Git,
or start procurement or production. `PASS` is not sending approval.

## Certified tuned_v4 source profile

The code was developed against quote 463 internal draft v4 with SHA-256
`179f62731adac46802db0bb3c3d8952072cba2d376a4a6b6f2790b7c1dc3832c`.
Its `B10` is an OOXML `inlineStr` with the exact value
`Плательщик: ТОО «Rich energy»`. Rows 17:19 are the approved commercial rows.
The certified item-table contract is B17:B116 numbering 1:100, the standard
line formula in every I17:I116, and no commercial data in C:H after the last
approved row. Every approved J cell is bound to its explicit `source_note` in
the Human Approval artifact; rows without notes and all trailing rows use the
certified empty-string formula.

## Required inputs

All inputs and the new output path must be outside the Git project:

- approved tuned_v4 internal draft XLSX;
- separately reviewed approval JSON;
- new client candidate XLSX path whose parent directory already exists.

The output must not already exist. The transformer never overwrites it.

## Approval schema

The strict schema version is:

```text
checked_clientization_approval.v0.2
```

The approval JSON binds the run to the exact internal draft SHA-256 and contains
the approved invoice metadata, VAT arithmetic, amount words and every item
field. Item rows must be contiguous from row 17. The approval must contain:

```json
{
  "commercial_price_approved": "yes",
  "clientization_approved": "yes",
  "sending_approved": "no"
}
```

The PTO engineer's manufacturing-lead-time decision has a separate audit trail:

```json
{
  "manufacturing_lead_time_approved_by": "Engineer name",
  "manufacturing_lead_time_approved_at": "2099-01-01T11:30:00+05:00",
  "manufacturing_lead_time_approval_role": "pto_engineer"
}
```

The engineer name must be non-empty, the timestamp must be valid ISO 8601 with
a timezone, and the role must be exactly `pto_engineer`. The general
`approved_by` remains the separate Human Approval for commercial price and
clientization and never substitutes for the PTO decision.

Every item contains exactly two note fields in addition to the commercial and
technical fields:

```json
{
  "source_note": null,
  "client_note": null
}
```

Both values must be null, or both must be non-empty UTF-8 strings.
`source_note` is the exact text certified in the internal draft; `client_note`
is the exact client-facing text separately approved by a human. The
transformer does not infer notes from item names, translate them, normalize
them or change their punctuation. A `client_note` containing an internal guard
token is rejected.

`source_note` and `client_note` may be identical, or `source_note` may be a
substring of `client_note`. Such text is allowed only when the complete cell
value is the exact approved `client_note` in its corresponding J cell. The same
exact `client_note` may appear in multiple J cells only when every such row is
explicitly approved with that value. Embedded, prefixed, suffixed, duplicated
or unreferenced occurrences are rejected.

Approval schema v0.1 must not be used for new runs.

The approval JSON is an external workflow artifact and must not be committed.

## Fail-closed processing order

1. Validate that inputs/output are outside Git and output is new.
2. Validate the exact approval JSON schema and Human Approval gates.
3. Verify the internal draft SHA-256.
4. Reconcile invoice metadata, every item field, formulas, total, VAT, amount
   words, commercial terms and every exact `source_note` against the approval.
   The manufacturing lead time and its separate signer/time/`pto_engineer`
   metadata are mandatory Human Approval data from the PTO engineer.
   Clientization reports that audit metadata, verifies that C123 exactly
   matches the approved term, and preserves C123 without calculating,
   normalizing or duplicating the term.
5. Create a hidden candidate by patching existing OOXML cells only.
6. Clear certified guard cells, keep G9:I13 clear, remove every source note and
   write each exact approved `client_note` only to its corresponding J cell.
   All other J17:J116 cells become physically empty and formula-free.
7. Remove unreferenced forbidden guard strings and approved source-note strings
   from `sharedStrings.xml`.
8. Structurally compare source/candidate worksheet XML. Only B9, certified
   guard cells, J17:J116 and approved C item-name cells may change; styles,
   row/column attributes, merges, views, print/page settings, drawings,
   hyperlinks and worksheet relationships must remain equivalent.
   Client-facing names and cleared guard/item-note cells must not contain formulas.
9. Scan the complete candidate package for any remaining guard token or
   `source_note`. Verify location-aware that every exact `client_note` occurs
   only in the approved J cell or cells. Equal and overlapping source/client
   text is permitted only inside those exact complete J values. A duplicate,
   prefix, suffix or embedded occurrence in another J cell, K130, another
   worksheet cell, shared string or OOXML part is a failure.
10. Reconcile client names, preserved technical composition, formulas, totals
    and VAT independently.
11. Verify input hashes again and atomically publish the new XLSX.

On any failure, no final output is published and the hidden candidate is
removed.

## Future command after separate commercial approval

Do not run this command until Igor has reviewed and approved the real approval
JSON:

```powershell
.\scripts\run_checked_clientization.ps1 `
  -InternalDraftXlsx "C:\outside-git\internal-draft.xlsx" `
  -ApprovalJson "C:\outside-git\checked-clientization-approval.json" `
  -OutputXlsx "C:\outside-git\client-candidate.xlsx"
```

After `PASS`, open the candidate and perform a manual visual and commercial
review. A separate Human Approval is still required before sending. PDF export
is intentionally outside this phase.
