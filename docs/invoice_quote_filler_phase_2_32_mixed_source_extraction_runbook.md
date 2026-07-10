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

## Command

Run from the repository root. Pass at least one source and use a new output
directory outside Git:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\extract_mixed_source_composition.py `
  --project-pdf "<PROJECT.pdf>" `
  --spec-workbook "<SPEC.xlsx>" `
  --output-dir "<NEW_TEMP_OUTPUT_DIR>"
```

For PDF-only or workbook-only use, omit the other source argument.

The output directory must not already exist. The source PDF/workbook remains
read-only and is never copied into the repository.

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
