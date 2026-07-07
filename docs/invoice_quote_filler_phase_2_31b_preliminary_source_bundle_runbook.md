# Phase 2.31b — preliminary composition source bundle verifier

## Status and purpose

`scripts/verify_preliminary_composition_source_bundle.py` verifies that an
AI-produced preliminary composition draft is bound to the exact raw source text
file it claims to analyze.

The verifier calculates SHA256 from the raw input text bytes and compares it
with `source.raw_input_sha256` inside the preliminary draft JSON. It also runs
the existing preliminary draft validator before the bundle can pass.

This phase is still preliminary only. It does not parse PDF, image or OCR input
itself. It does not calculate price, create commercial CSV, create КП, export a
client-style file, approve production or authorize sending.

## Command

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\verify_preliminary_composition_source_bundle.py `
  --raw-input-text "C:\outside-git\raw-request.txt" `
  --draft-json "C:\outside-git\preliminary-composition-draft.json"
```

Report markers:

```text
PRELIMINARY_COMPOSITION_SOURCE_BUNDLE_REPORT_START
PRELIMINARY_COMPOSITION_SOURCE_BUNDLE_REPORT_END
```

Exit code:

- `0` only when the report status is `PASS`;
- `1` when the report status is `FAIL`.

## What PASS means

`PASS` means only:

- the raw input text exists and is UTF-8 readable;
- the draft JSON exists and passes the preliminary composition draft validator;
- the raw input SHA256 exactly matches `source.raw_input_sha256`;
- the safety boundary remains preliminary only.

`PASS` does not mean confirmed composition, price approval, commercial CSV
approval, client-ready КП, production approval or sending approval.

Igor must confirm the composition before any price calculator, commercial CSV
or client-style export step.

## Checks

The report includes these checks:

```text
raw input readable
draft validation
source hash match
safety boundary
```

The report may show:

- calculated raw input SHA256;
- draft `source.raw_input_sha256`;
- `source_type`;
- status and check names;
- short red flags.

The report must not print raw input text or long evidence blocks from the draft.

## Example PASS report

```text
PRELIMINARY_COMPOSITION_SOURCE_BUNDLE_REPORT_START

Status:
PASS

Mode:
preliminary composition source bundle verification only

Checks:
raw input readable: pass
draft validation: pass
source hash match: pass
safety boundary: pass

Source:
source_type: text_request
calculated raw_input_sha256: 1111111111111111111111111111111111111111111111111111111111111111
draft raw_input_sha256: 1111111111111111111111111111111111111111111111111111111111111111

Red flags:
none

Commercial status:
not confirmed composition; not price approval; not client-ready КП

Human Approval:
Igor confirmation required before price calculation or commercial CSV

PRELIMINARY_COMPOSITION_SOURCE_BUNDLE_REPORT_END
```

## Example FAIL report

```text
PRELIMINARY_COMPOSITION_SOURCE_BUNDLE_REPORT_START

Status:
FAIL

Mode:
preliminary composition source bundle verification only

Checks:
raw input readable: pass
draft validation: pass
source hash match: fail
safety boundary: pass

Source:
source_type: text_request
calculated raw_input_sha256: 2222222222222222222222222222222222222222222222222222222222222222
draft raw_input_sha256: 1111111111111111111111111111111111111111111111111111111111111111

Red flags:
raw input SHA256 mismatch

Commercial status:
not confirmed composition; not price approval; not client-ready КП

Human Approval:
Igor confirmation required before price calculation or commercial CSV

PRELIMINARY_COMPOSITION_SOURCE_BUNDLE_REPORT_END
```

## Operator notes

Use this verifier only after a preliminary AI draft has been created with a
`source.raw_input_sha256` value. The raw input text should be the exact UTF-8
source bytes used for that draft.

Do not create XLSX, CSV, client, generated or temporary files from this phase.
Do not commit or push without separate Igor approval.
