# Reusable Case → DINVA document bridge

`scripts/build_dinva_document_from_case.py` produces the existing
`dinva_quote_invoice_document.v0.2` for arbitrary QUOTE Cases. It copies approved
business values, validates arithmetic, and never calculates or replaces prices.
It does not change a presentation profile, render XLSX/PDF, or send documents.
Invoice519 and its historical producer remain separate and unchanged.

## Inputs and provenance

Both inputs are external, independently SHA-bound JSON files. Duplicate keys,
unknown fields, non-finite numbers, missing approvals and source drift fail closed.

The normalized Case snapshot has schema `dinva_case_document_source.v0.1`:

- `case_id`;
- `metadata`: `document_type` (QUOTE), `document_number`, `document_date`,
  `currency`, `payer`, `object_name`, `basis`, `apparatus_heading`, `sections`,
  `vat`, `amount_words`, `signatures`, using the existing document field shapes;
- ordered `items`: unique `item_id`, `name`, `unit`, `quantity`,
  `detailed_technical_composition`, `enclosure`, `approved_unit_price_kzt`,
  `approved_line_total_kzt`;
- `approved_grand_total_kzt`;
- `terms`: `payment`, `delivery`, `manufacturing_lead_time`, `validity`,
  ordered `commercial_lines` (strings);
- nonempty `source_bindings`: unique `role`, absolute `path`, exact `sha256` for
  confirmed Case / project / pricing / Human Decision evidence. Values and upstream
  roles are operator-supplied facts, not inferred from a filename or status flag.

The approved lead-time text must appear verbatim exactly once in commercial_lines.
No start condition or normalization is inferred. Optional fields may be null only
where the existing document contract allows it. Payer, VAT and other required
business fields require an authoritative source or Human Decision.
The snapshot is a normalized, reviewed representation of an approved Case; it is
not a preliminary extraction or an automatic promotion of extraction confidence.

Igor's reusable commercial-fields decision permits an unassigned QUOTE number:
missing/null/empty source number becomes canonical JSON null. The existing v0.2
document schema, renderer and independent validator accept missing/null numbers
only for QUOTE; its title omits the number and the `№` marker entirely. INVOICE
and QUOTE_INVOICE still require an assigned number. No temporary number is generated.

Absent quote date uses the actual DINVA factory calendar date (UTC+05:00);
an explicit authoritative date remains unchanged. Default delivery is exactly
`EXW г. Астана`. Default signatures are director `Никольченко И.В.` and executor
`Инженер-Электрик ПТО Марат А.К.` per the same direct Igor decision. Explicit
case overrides are preserved. No payment, validity or historical commercial
conditions are inherited. A delivery value not already represented in commercial
lines is included verbatim once. Default delivery provenance points to
`DEFAULT_DELIVERY` in the SHA-bound producer policy source, not to an absent Case
field. All default values are covered by the approved business fingerprint, and
the policy source is reread together with the Case sources before publication.

The separate `dinva_case_document_approval.v0.1` record contains exactly:
`schema_version`, `case_id`, `authority` (IGOR_DIRECT_HUMAN_APPROVAL),
`approved_by` (Igor), timezone-bearing `approved_at`, `approval_id`,
`approved_case_source_sha256`, `approved_document_fingerprint`,
`technical_composition_approved`, `prices_approved`, `commercial_terms_approved`,
`rendering_authorized` (all true), `client_send_authorized` (false).
It binds the exact snapshot bytes and complete business fingerprint, not merely
the Case ID or grand total. Approval records assert contract claims; they do not
create Human Approval or permission to execute a publication token.

Output apparatus and commercial text cite the snapshot SHA and exact JSON pointer.
The approval record and every upstream source are included in document provenance.
The producer invokes both existing renderer and independent document validators.

## Read-only preflight and publication

CLI arguments: `--case-source`, `--case-source-sha256`, `--case-approval`,
`--case-approval-sha256`, `--output`. Default mode reads and validates inputs,
checks a new outside-Git JSON output path with an existing parent, and prints the
candidate SHA/fingerprint. It creates no files and no authorization token.

The Python API also accepts `preview=True` with in-memory Snapshot bytes and new
prospective input paths. It validates business data, exact approval bindings and
all existing upstream/policy sources without writing the prospective inputs.
Such a plan is marked unmaterialized and cannot be published. The source snapshot
and approval record need their exact real-artifact Human Approval first; then the
normal materialized preflight must be run anew. The CLI offers no preview bypass.

Real snapshot/approval materialization and final document publication require
their corresponding exact direct Human Approval. Never manufacture approval
records from PASS/status fields. Supply externally reviewed records only.

`--publish --authorization <external exact token>` is a separate mutation mode.
Token fields are `IGOR_DINVA_CASE_DOCUMENT_PUBLICATION_AUTHORIZED`,
`ACTION=IMMUTABLE_DOCUMENT_PUBLICATION`, `CASE_SHA256`, `APPROVAL_SHA256`,
`DOCUMENT_FINGERPRINT`, `OUTPUT_PATH_SHA256` (SHA of UTF-8 resolved output path),
joined in this order by `|`. It is bound to this exact action/subject/output and
does not authorize renderer, PDF export, client send or downstream work.

Publication stages and fsyncs bytes, rereads all inputs, atomically hard-links
without overwrite, rereads sources/output, and rolls back only its own linked
output on failure. Existing output and replay fail closed.

After separate renderer authorization, use the existing Classic v0.5 renderer
and independent validator with the published document SHA. Their existing
profile/source/layout/OOXML gates and Human visual review remain required.
Synthetic tests may publish/render only under pytest temporary directories.
