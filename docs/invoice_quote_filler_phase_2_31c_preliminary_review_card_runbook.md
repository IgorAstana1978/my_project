# Phase 2.31c - preliminary composition Igor review card

## Status and purpose

`scripts/build_preliminary_composition_review_card.py` creates a Markdown review
card for Igor from a source-bound preliminary composition draft.

This is an operator review layer after source bundle verification:

```text
raw request/project text
-> preliminary composition draft JSON
-> validate_preliminary_composition_draft.py
-> verify_preliminary_composition_source_bundle.py
-> build_preliminary_composition_review_card.py
```

The card helps Igor review what the AI understood, which switchboards and
cabinets were guessed, which components were extracted, what evidence supports
the draft, and which red flags or assumptions need manual resolution.

## Command

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\build_preliminary_composition_review_card.py `
  --raw-input-text "C:\outside-git\raw-request.txt" `
  --draft-json "C:\outside-git\preliminary-composition-draft.json" `
  --output-md "C:\outside-git\preliminary-composition-review-card.md"
```

Report markers:

```text
PRELIMINARY_COMPOSITION_REVIEW_CARD_REPORT_START
PRELIMINARY_COMPOSITION_REVIEW_CARD_REPORT_END
```

Exit code:

- `0` only when the review card is created successfully;
- `1` on any failure.

## What PASS means

`PASS` means only:

- the source bundle verifier passed;
- the draft JSON was readable;
- the output Markdown path was outside Git and did not already exist;
- the review card was written.

`PASS` does not mean confirmed composition, price approval, commercial CSV
approval, client-ready КП, production approval or sending approval.

Igor must confirm the composition before any price calculation or commercial CSV
step.

## Output policy

The output Markdown must be outside the Git project tree. The script fails if:

- `--output-md` already exists;
- `--output-md` is inside the project;
- the output parent directory does not exist;
- source bundle verification fails.

If verification fails, no Markdown file is created.

## Review card contents

The card includes:

- source metadata;
- preliminary safety flags;
- item summaries;
- cabinet guesses;
- component table;
- confidence values;
- short evidence summaries;
- red flags and assumptions;
- Igor confirmation checklist;
- final safety footer.

The card must not include raw request/project text. Evidence is shortened to
160 characters per evidence item.

## Safety boundaries

This phase does not:

- calculate price;
- create commercial CSV;
- create КП or XLSX;
- call a client-style exporter or launcher;
- approve sending;
- approve production.

The review card is for Igor's composition review only.

## Example PASS report

```text
PRELIMINARY_COMPOSITION_REVIEW_CARD_REPORT_START

Status:
PASS

Mode:
preliminary composition Igor review card only

Checks:
source bundle verification: pass
output policy: pass
draft read: pass
review card write: pass
safety boundary: pass

Red flags:
none

Output:
C:\outside-git\preliminary-composition-review-card.md

Commercial status:
not confirmed composition; not price approval; not client-ready КП

Human Approval:
Igor confirmation required before price calculation or commercial CSV

PRELIMINARY_COMPOSITION_REVIEW_CARD_REPORT_END
```

## Example FAIL report

```text
PRELIMINARY_COMPOSITION_REVIEW_CARD_REPORT_START

Status:
FAIL

Mode:
preliminary composition Igor review card only

Checks:
source bundle verification: fail
output policy: fail
draft read: fail
review card write: fail
safety boundary: pass

Red flags:
source bundle verifier failed

Output:
not created

Commercial status:
not confirmed composition; not price approval; not client-ready КП

Human Approval:
Igor confirmation required before price calculation or commercial CSV

PRELIMINARY_COMPOSITION_REVIEW_CARD_REPORT_END
```

## Operator notes

Use this card only to review a source-bound preliminary draft. Igor must confirm
or reject the composition before any next step.

Do not create XLSX, CSV, client, generated or temporary files from this phase.
Do not commit or push without separate Igor approval.
