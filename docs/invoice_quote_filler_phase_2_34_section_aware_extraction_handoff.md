# Phase 2.34 — section-aware extraction contract handoff

## Scope

This phase adds a versioned multi-PDF intake beside the existing Phase 2.32
single-PDF/workbook workflow. It does not process the real project 2024/086,
perform commercial mapping, calculate prices, or generate a quote.

The existing `--project-pdf` workflow and
`preliminary_composition_draft.v0.1` output remain unchanged.

## Intake contract

The new CLI option is `--section-aware-intake <JSON>`. It is mutually exclusive
with `--project-pdf` and `--spec-workbook`.

The root object is strict and has this form:

```json
{
  "intake_version": "section_aware_extraction_intake.v0.1",
  "project_id": "2024/086",
  "source_documents": [
    {
      "path": "section-13-eom.pdf",
      "source_document_id": "section-13-eom",
      "section_id": "13",
      "discipline": "ЭОМ",
      "source_role": "project_pdf"
    }
  ]
}
```

All fields are required and must be non-empty strings. Unknown fields are
rejected. Only PDF sources and `source_role = project_pdf` are supported in this
pilot. Relative paths are resolved against the intake JSON directory.

`source_document_id` must match `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`. IDs must be
unique within an intake. A repeated ID is rejected, including when the repeated
records contain conflicting metadata. The ID is logical and stable: absolute
paths are never part of merge identity. The resolved path, original intake path,
file name, and SHA-256 remain separate canonical source-document metadata.

## Output contract and identity

The new draft version is
`preliminary_composition_draft.section_aware.v0.1`. Its canonical source records
are stored in `source.source_documents`. Items, components, and provenance carry
the required section-aware context and reference the canonical record through
`source_document_id`; they do not copy the absolute source path.

The exact board merge identity is the structured tuple:

```text
(project_id, section_id, discipline, source_document_id,
 normalized_designation)
```

Evidence may merge only inside that identity. Equal normalized designations in
different projects, sections, disciplines, or source documents remain separate.
The validator reconstructs each item's identity from its provenance and rejects
missing, mixed, unknown, or inconsistent context fail-closed. Components and
their provenance must resolve to the same item identity.

The validator additionally rejects duplicate item identities even when their
`item_id` values differ, rejects duplicate `component_id` values across the
whole draft, and requires every provenance `page` to be a positive integer that
exists in the referenced canonical source document's `pages` metadata. These
checks apply equally to item, component, and conflict provenance.

## Known limitation

The pilot cannot distinguish two physical items with the same normalized
designation inside one source document. No synthetic `item_occurrence_id` is
introduced because the current extractor cannot derive one reliably.
