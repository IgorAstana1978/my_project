# Phase 2.32 - PDF-first mixed-source composition extraction pilot

## Purpose

The checked operator run accepts a text-layer PDF project, an Excel
specification, or both. It creates one preliminary composition bundle for Igor
review. It does not calculate a price, create commercial CSV or КП, approve
sending, procurement, or production.

Supported inputs:

- `.pdf` with a usable text layer, including mixed text/image-only documents;
- `.xlsx` and `.xlsm` through the existing `openpyxl` dependency;
- `.xls` through the existing `xlrd` dependency.

OCR, scans without a text layer, DWG/DXF, LLM APIs, cloud services, and
engineering substitutions are not supported.

## Canonical Case command

For normal operator use, publish through the checked Case wrapper. The Case ID
must match `CASE-[A-Z0-9]+(?:-[A-Z0-9]+)*`, with a maximum length of 128
characters. The canonical root must already exist at:

```text
%USERPROFILE%\Documents\production_ai_cases
```

Run from the repository root and pass at least one source:

PDF only:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\extract_mixed_source_composition_case.py `
  --case-id "CASE-EXAMPLE-PDF" `
  --project-pdf "<PROJECT.pdf>"
```

Excel only:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\extract_mixed_source_composition_case.py `
  --case-id "CASE-EXAMPLE-XLSX" `
  --spec-workbook "<SPEC.xlsx>"
```

PDF and Excel:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\extract_mixed_source_composition_case.py `
  --case-id "CASE-EXAMPLE-01" `
  --project-pdf "<PROJECT.pdf>" `
  --spec-workbook "<SPEC.xlsx>"
```

Prerequisites: use the project virtual environment, keep the canonical root in
place, select a new valid Case ID, and preserve the source files at their
current paths. The wrapper deliberately has no `--output-dir`: it can publish
only to the exact canonical child directory
`%USERPROFILE%\Documents\production_ai_cases\<CASE-ID>`.

The final Case directory must not already exist. Existing or partial Case
directories are never overwritten, merged, repaired, or deleted. A failure in
that situation requires Igor to inspect the directory manually.

## Governed versioned rerun of an existing Case

For a rotated CAD specification PDF, an existing Case may receive one new
immutable `extraction-V001` child without changing its original three files.
The version is explicit; `V001` is an example, and a published version cannot
be reused. Supply selection comes only from an exact governed intake. The
intake is preliminary provenance, not technical or commercial approval.

```powershell
.\.venv\Scripts\python.exe .\scripts\extract_mixed_source_composition_case.py `
  --case-id "<EXISTING-CASE-ID>" `
  --project-pdf "<SAME-PDF>" `
  --extraction-version "V001" `
  --intake-json "<NEW-GOVERNED-INTAKE.json>"
```

The UTF-8 intake has exact fields `schema_version`, `case_id`,
`extraction_version`, `project_pdf_path`, `project_pdf_sha256`,
`base_manifest_sha256`, `client_request`, `human_decisions`,
`requested_supply`, and `excluded_components`. The schema is
`governed_case_extraction_intake.v0.1`. Request and decision records contain
`text`, `source_locator`, and the SHA-256 of the exact UTF-8 text in
`text_sha256`; supply and exclusion records contain `designation` and a
positive integer `quantity`. The operator must preserve the actual message
and decision provenance. A text hash proves byte integrity, not that a client
or Igor authored the text. Review that authority separately.

The runner validates PDF and original Case manifest hashes, parses rotated
specification rows, distinguishes requested rows, excluded components, and
project context, and publishes through an owned staging directory only after
all five existing extractor checks and the new version binding pass. The
new child contains the normal manifest/draft/review plus
`governed-intake.json` and `version-binding.json`. The manifest includes the
intake hash and source-backed row classifications. Unresolved component,
cabinet, scheme, low-confidence evidence, and governed decisions remain red
flags for Igor. The Human Decision text, including any reserved meter-space
requirement, is preserved in the bound intake; it is not an installed or
priced component.
No price or quote permission is created.

## Checked publication

The wrapper calls the existing Phase 2.32 extractor directly, without a
subprocess. It atomically creates its own unique owner container inside the
canonical root, then writes to an absent `bundle` child. Before publication it
requires:

- extractor status `PASS` and all required structured validation checks `pass`;
- exactly the three expected, non-empty, regular output files;
- no extra files, directories, symlinks, or reparse-point-like entries;
- the final Case directory still to be absent.

Only then is the complete `bundle` directory renamed to the final Case
directory. On an expected failure the wrapper removes only the owner container
that it proved it created. A pre-existing or ownership-ambiguous path is never
removed automatically; its exact path is reported for manual inspection. A
cleanup failure or publication race is also reported, and an existing final
directory is preserved. After publication the final Case directory is never a
cleanup target; only the verified-empty owner container may be removed.

The source PDF and workbook remain read-only. They are not copied into the
Case directory or the repository. The wrapper does not run a calculator,
commercial CSV/XLSX or КП generation, APIs, clipboard operations, confirmed
composition building, production-envelope building, sending, procurement, or
production actions.

## Operator review and explicit stop

After a `PASS`, open the review card without modifying the source artifacts:

```powershell
notepad `
  "$env:USERPROFILE\Documents\production_ai_cases\CASE-EXAMPLE-01\igor-review-card.md"
```

Stop after reviewing the card. Extraction is not Human Approval and does not
confirm the technical composition. The confirmed-composition builder is a
separate possible next step only after Igor's explicit decision; this wrapper
does not run it automatically.

Because originals are not copied, retain the original PDF/workbook unchanged.
If an original is later deleted, the manifest retains its recorded SHA-256 and
provenance, but the exact source bytes can no longer be re-read or independently
verified from the Case bundle alone.

## Low-level diagnostic command

The underlying extractor remains available for controlled diagnostics. Pass at
least one source and use a new output directory outside Git:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\extract_mixed_source_composition.py `
  --project-pdf "<PROJECT.pdf>" `
  --spec-workbook "<SPEC.xlsx>" `
  --output-dir "<NEW_TEMP_OUTPUT_DIR>"
```

For PDF-only or workbook-only use, omit the other source argument.

The output directory must not already exist. Prefer the canonical Case wrapper
for normal operator use.

## Outputs

The output directory contains:

- `source-bundle-manifest.txt` - source file hashes and PDF/workbook inspection
  metadata, used by the existing source-bundle verifier;
- `preliminary-composition-draft.json` - the existing
  `preliminary_composition_draft.v0.1` contract with optional, backwards-
  compatible extraction fields for provenance, conflicts, missing values, and
  summary counts;
- `igor-review-card.md` - the existing Igor review card, grouped by
  switchboard, with source locators and a separate `Требует проверки Игоря`
  section.

PDF pages are classified as `text_available`, `low_text_confidence`,
`image_only`, `unreadable`, `encrypted_or_protected`, or `corrupt`. Only pages
with usable text participate in extraction; every other page remains visible
for OCR or manual review.

An extraction `PASS` means only that the preliminary bundle passed the existing
validator, exact manifest hash verification, and review-card builder. Igor must
still separately approve composition, price, term, commercial CSV, final КП,
sending, procurement, and production.
