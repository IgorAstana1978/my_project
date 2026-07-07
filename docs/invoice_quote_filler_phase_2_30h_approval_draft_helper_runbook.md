# Phase 2.30h — client-style approval JSON draft helper

## Status and purpose

`scripts/create_client_style_approval_draft.py` creates only a reviewable
client-style approval JSON **draft** outside Git.

The helper reduces manual copy-paste and SHA256 mistakes by calculating these
hashes automatically:

- `commercial_csv_sha256`;
- `internal_draft_xlsx_sha256`;
- `template_sha256`.

The helper does not:

- approve anything;
- create commercial approval;
- authorize sending;
- create XLSX output;
- call the exporter;
- call the launcher;
- call Git.

Before using `scripts/run_client_style_invoice_export.ps1`, Igor must manually
inspect, edit if needed and confirm the approval JSON. The draft is not approval
itself.

## Required safety boundaries

All real inputs and the output approval JSON draft must be outside Git:

- approved commercial CSV;
- internal draft XLSX;
- approved client-style template XLSX;
- output approval JSON draft.

Do not commit XLSX, CSV, approval JSON, generated, client or temp files.

`PASS` from this helper means only that the draft JSON was created. It is not
commercial approval and not sending approval.

## Required arguments

```text
--commercial-csv
--internal-draft-xlsx
--template-xlsx
--output-json
--approval-id
--approved-by
--approved-at
--invoice-number
--invoice-date
--payer-name
--vat-text-approved
--payment-terms-approved
--delivery-terms-approved
--validity-terms-approved
--return-terms-approved
--signer-name
--signer-title
--approval-note
```

Optional:

```text
--object-name
```

When `--object-name` is not supplied, the helper writes `object_name: null`.
That keeps the draft compatible with
`scripts/preflight_client_style_invoice_export.py`.

## Example command

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\create_client_style_approval_draft.py `
  --commercial-csv "C:\outside-git\approved-commercial.csv" `
  --internal-draft-xlsx "C:\outside-git\internal-draft.xlsx" `
  --template-xlsx "C:\Users\IgorN\Downloads\client_style_template_phase_2_30e\client_style_invoice_template_candidate.xlsx" `
  --output-json "C:\outside-git\client-style-approval.draft.json" `
  --approval-id "APPROVAL-EXAMPLE-001" `
  --approved-by "Igor" `
  --approved-at "2099-01-01T12:00:00+05:00" `
  --invoice-number "TEST-001" `
  --invoice-date "2099-01-01" `
  --payer-name "SAFE-PAYER" `
  --vat-text-approved "НДС включён" `
  --payment-terms-approved "Условия оплаты утверждены Игорем" `
  --delivery-terms-approved "Условия поставки утверждены Игорем" `
  --validity-terms-approved "Срок действия утверждён Игорем" `
  --return-terms-approved "Условия возврата утверждены Игорем" `
  --signer-name "SAFE-SIGNER" `
  --signer-title "SAFE-TITLE" `
  --approval-note "Условия договора утверждены Игорем"
```

The helper fails if:

- the output JSON already exists;
- the output JSON would be inside Git;
- the output parent directory does not exist;
- any required input does not exist;
- any required input is inside Git.

Reports are bounded by:

```text
CLIENT_STYLE_APPROVAL_DRAFT_REPORT_START
CLIENT_STYLE_APPROVAL_DRAFT_REPORT_END
```

The report does not print full approved commercial terms.

## After the draft is created

1. Open the draft approval JSON outside Git.
2. Igor manually reviews every field and commercial term.
3. Igor confirms the approval JSON only after review.
4. Then use `scripts/run_client_style_invoice_export.ps1` with the reviewed
   approval JSON.
5. If the exporter returns `PASS`, still open the XLSX candidate and perform a
   manual Igor check.
6. Obtain a separate Human Approval before sending anything to a client.

Generated XLSX candidates are still only candidates. `PASS` never authorizes
sending.
