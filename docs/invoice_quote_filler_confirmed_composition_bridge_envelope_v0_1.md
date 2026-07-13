# Confirmed composition bridge envelope v0.1

## Purpose

`confirmed_composition_bridge_envelope.v0.1` is a thin, read-only transfer
envelope. It binds one operational case and one Igor approval record to the
exact bytes of a separate confirmed composition artifact.

The envelope is not an approved composition packet. The separate
`confirmed_composition_artifact.v0.1` remains the only source of truth for the
approved technical composition. The envelope does not duplicate items,
components, cabinets, quantities, technical composition, prices, commercial
data, quote content, or production instructions.

The next downstream consumer is not connected in this phase.
`production-ai-assistant` and cross-project bridge implementations are not
changed.

## Schema

Only the following structure is accepted. Unknown fields at any level fail
validation.

```json
{
  "schema_version": "confirmed_composition_bridge_envelope.v0.1",
  "case": {
    "case_id": "CASE-2099-001",
    "customer_label": "Synthetic operational label",
    "object_name": "Synthetic object"
  },
  "confirmed_composition": {
    "schema_version": "confirmed_composition_artifact.v0.1",
    "artifact_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  },
  "supply_boundary": {
    "status": "approved_by_igor",
    "description": "Synthetic supply boundary approved for transfer only.",
    "approved_by_igor": true
  },
  "approval": {
    "approval_record_id": "APPROVAL-SYNTHETIC-001",
    "approved_by": "Igor",
    "approved_at": "2099-01-01T12:30:00+05:00",
    "approval_channel": "synthetic-example",
    "scope": "transfer_confirmed_composition_for_calculator_input_draft_only"
  },
  "safety": {
    "status": "confirmed_composition_bridge_only",
    "transfer_confirmed_composition_only": true,
    "price_approved_by_igor": false,
    "quote_generation_authorized": false,
    "client_send_authorized": false,
    "production_action_authorized": false
  }
}
```

The hash above is synthetic documentation data. It does not identify a real
artifact or approval record.

## Required constants

- Root `schema_version` is
  `confirmed_composition_bridge_envelope.v0.1`.
- `confirmed_composition.schema_version` is
  `confirmed_composition_artifact.v0.1`.
- `supply_boundary.status` is `approved_by_igor` and
  `supply_boundary.approved_by_igor` is `true`.
- `approval.scope` is
  `transfer_confirmed_composition_for_calculator_input_draft_only`.
- `safety.status` is `confirmed_composition_bridge_only` and
  `safety.transfer_confirmed_composition_only` is `true`.
- Price, quote generation, client sending, and production authorization flags
  are all exactly `false`.

Any commercial or production authorization set to `true` fails validation.
Supply-boundary approval confirms only the boundary of supply. It is not price
approval and does not approve quote generation, client sending, procurement,
or production.

## Case and approval

`case.case_id` uses the conservative grammar
`CASE-[A-Z0-9]+(?:-[A-Z0-9]+)*` and is limited to 128 characters. This permits
uppercase alphanumeric segments separated by single hyphens and excludes free
text, path traversal, whitespace, and control characters.

`case.customer_label` is an operational label only. It is not a legal payer or
legal customer identity and must not be used as the basis for an invoice or
quote. `case.object_name` is also required and non-empty.

The approval record ID, approver, channel, and timestamp must be non-empty. The
timestamp must be ISO 8601 with a timezone offset or `Z`. An approval record
authorizes only the exact transfer scope stated above; it is not an executable
approval token and does not authorize price, quote generation, client sending,
procurement, or production.

## SHA-256 binding

`confirmed_composition.artifact_sha256` is exactly 64 lowercase hexadecimal
characters. The validator computes SHA-256 from the exact original bytes of
the file passed with `--confirmed-composition-json`. It does not reserialize
JSON before hashing.

After the hash comparison, the existing
`validate_confirmed_composition_artifact()` validator must return `PASS`. The
confirmed artifact root must use `confirmed_composition_artifact.v0.1`, and its
root `red_flags` must be present as an empty list.

## CLI

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\validate_confirmed_composition_bridge_envelope.py `
  --envelope-json "C:\outside-git\bridge-envelope.json" `
  --confirmed-composition-json "C:\outside-git\confirmed-composition.json"
```

Both inputs must exist as readable regular files containing strict UTF-8 JSON
objects. The validator is read-only: it prints one delimited report and creates
no output files.

Exit code `0` means `PASS`. A non-zero exit code means `FAIL`.

## Fail-closed behavior

Validation fails for missing or unreadable files, malformed JSON, non-UTF-8,
non-object roots, missing or unknown fields, invalid Case IDs, incomplete
approval metadata, timestamps without timezone, the wrong approval scope,
unapproved supply boundaries, invalid or mismatched SHA-256, wrong schema
versions, an existing confirmed-artifact validator failure, and missing,
non-list, or non-empty confirmed-artifact `red_flags`.

The envelope also fails if it contains technical payload fields such as
`items`, `components`, `cabinet`, or `quantity`, or commercial/production data
such as price, totals, commercial CSV, quote content, or production
instructions. No ambiguity is repaired automatically.

## Human Approval boundary

A `PASS` report means only that the thin bridge envelope safely identifies an
exact, separately validated confirmed composition artifact for a future
calculator-input-draft consumer. It does not approve price, quote generation,
client sending, procurement, reservation, prepayment, or production. Human
Approval by Igor remains mandatory for those actions.
