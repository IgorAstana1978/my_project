# Phase 2.30f — one-item client-style invoice exporter

## Status and purpose

`scripts/export_client_style_invoice.py` creates a client-style XLSX
**candidate** for exactly one approved commercial item.

The exporter does not:

- approve a price or commercial terms;
- create a multi-item invoice;
- replace the internal draft writer;
- send a file to a client;
- provide sending approval.

`PASS` means only that the candidate passed the automated preflights and
reconciliation. Before sending, Igor must inspect the generated XLSX manually
and a separate Human Approval is required.

## Safe workflow

```text
price calculator
→ preliminary price report
→ Igor approval
→ approved commercial CSV
→ internal draft XLSX
→ Igor approval artifact
→ one-item client-style XLSX candidate
→ manual Igor check
→ separate Human Approval before sending
```

The approved template, production template contract, all commercial inputs,
approval artifact, internal draft and output must be outside Git.

Approved Phase 2.30e template:

```text
C:\Users\IgorN\Downloads\client_style_template_phase_2_30e\
client_style_invoice_template_candidate.xlsx
```

Approved template SHA256:

```text
5c39bc41adf0ae7a754c67c2590e8fa8346e3ec3f14ff842e346e74a8315f6e9
```

Matching template contract:

```text
C:\Users\IgorN\Downloads\client_style_template_phase_2_30e\
client_style_invoice_template_contract.candidate.json
```

The template hash must match both the approval artifact and template contract.

## Required arguments

```text
--commercial-csv
--internal-draft-xlsx
--template-xlsx
--template-contract-json
--approval-json
--output-xlsx
```

Example:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\export_client_style_invoice.py `
  --commercial-csv "C:\outside-git\approved-commercial.csv" `
  --internal-draft-xlsx "C:\outside-git\internal-draft.xlsx" `
  --template-xlsx "C:\Users\IgorN\Downloads\client_style_template_phase_2_30e\client_style_invoice_template_candidate.xlsx" `
  --template-contract-json "C:\Users\IgorN\Downloads\client_style_template_phase_2_30e\client_style_invoice_template_contract.candidate.json" `
  --approval-json "C:\outside-git\client-style-approval.json" `
  --output-xlsx "C:\outside-git\client-style-candidate.xlsx"
```

The output parent directory must already exist. The exporter never overwrites
an output.

## Fail-closed order

The exporter performs these stages in order:

1. Import and run `preflight_client_style_invoice_export.py`.
2. Import and run `preflight_client_style_invoice_template_contract.py`.
3. Validate the strict commercial CSV and enforce exactly one item.
4. Read only approved fields from the approval artifact.
5. Discover exact term targets from the approved template placeholders.
6. Create a hidden candidate by patching existing OOXML cells.
7. Reconcile the hidden candidate read-only.
8. Atomically publish the final output only after reconciliation passes.

If any stage fails:

- final output is not published;
- the hidden candidate is removed;
- existing outputs are not overwritten or deleted;
- template and every input remain unchanged.

## Commercial CSV contract

The exact, ordered schema is:

```text
name
unit
quantity
instruments_and_devices
cabinet_type_dimensions_material
unit_price_kzt
price_includes_vat
price_confirmed_by_igor
```

Requirements:

- exactly one data row;
- no missing, duplicate or extra columns;
- no empty required values;
- positive integer quantity;
- positive integer unit price;
- `price_includes_vat` must be exact `yes`;
- `price_confirmed_by_igor` must be exact `yes`.

## Template-driven mapping

The exporter reads sheet name, item row, item columns and primary cell
coordinates from the template contract.

If invoice number and date use the same cell, the value is:

```text
Счёт № {invoice_number} от {invoice_date}
```

The current approved template uses:

- header: `C9`;
- payer: `C10`;
- item: `B16:I16`;
- total: `I17`;
- amount words and approved VAT text: `C19`;
- signer title/name: `C29` and `F29`.

The exporter does not guess term cells. It requires exactly one occurrence of
each approved template placeholder:

- `[условия оплаты]`;
- `[условия возврата]`;
- `[условия изменения спецификации / срок действия]`;
- `[условия договора]`;
- `[условия поставки / срок изготовления]`.

The contract terms placeholder receives the approved `approval_note`. No
default terms or historical invoice text are allowed.

The line total and total are numeric values:

```text
quantity × unit_price_kzt
```

Amount words are calculated deterministically with the same Russian integer
wording logic as the commercial writer. They are not accepted from the
approval artifact.

## Reconciliation

Before publication, reconciliation verifies:

- output candidate exists outside Git and opens;
- expected worksheet exists;
- invoice number, date and payer match the approval artifact;
- exactly one item is represented;
- quantity and unit price match the CSV;
- line total and total equal `quantity × unit_price_kzt`;
- amount words correspond to the numeric total;
- VAT text is exactly the approved text;
- approved terms are in their discovered cells;
- signer title and name match approval;
- template placeholders are absent without exception;
- historical forbidden tokens are absent unless the same token is represented
  by a value explicitly approved or generated for the current export;
- all input files retain their pre-export hashes;
- commercial CSV, internal draft and template still match approval hashes.

The legacy-token scan blocks unapproved static leftovers. It does not reject a
value that comes from the current approved commercial CSV, approval artifact,
or a deterministic generated value such as the line total or amount words.
For example, an approved current unit price of `44512` is allowed. `НДС 16%`
is allowed only when it is present in `vat_text_approved`, while an unrelated
`TDK Energy` or `EXW` left in the template still fails reconciliation.
Placeholders always fail and never receive a dynamic exception.

Any reconciliation failure prevents publication and removes the hidden
candidate.

## Report and operator decision

Reports are bounded by:

```text
CLIENT_STYLE_INVOICE_EXPORT_REPORT_START
CLIENT_STYLE_INVOICE_EXPORT_REPORT_END
```

Reports show check statuses, red flags and output path, but do not print full
approved client terms.

Exit codes:

- `0`: automated `PASS`;
- `1`: fail-closed `FAIL`.

Even after exit code `0`:

1. keep the XLSX as a client-style candidate;
2. open it and perform a manual Igor check;
3. obtain separate Human Approval;
4. only then consider a separate sending action.

The exporter itself never sends files.
