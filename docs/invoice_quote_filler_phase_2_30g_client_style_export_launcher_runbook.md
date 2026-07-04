# Phase 2.30g — checked client-style invoice export launcher

## Status and purpose

`scripts/run_client_style_invoice_export.ps1` is the checked PowerShell
launcher for the stable one-item client-style invoice exporter.

The launcher creates only a client-style XLSX **candidate**. It does not:

- provide commercial approval;
- provide sending approval;
- create an approval JSON;
- create a commercial CSV;
- create an internal draft;
- send anything to a client.

`PASS` is not commercial approval and is not sending approval. After `PASS`,
Igor must inspect the generated XLSX manually. A separate Human Approval is
required before sending.

## Required inputs

The operator must provide:

- `CommercialCsv`: approved one-item commercial CSV outside Git;
- `InternalDraftXlsx`: approved internal draft XLSX outside Git;
- `ApprovalJson`: approved client-style approval artifact outside Git;
- `OutputXlsx`: new candidate output path outside Git.

The output must not already exist. The exporter fail-closes and does not
overwrite it.

## Approved defaults

The default approved template is:

```text
C:\Users\IgorN\Downloads\client_style_template_phase_2_30e\client_style_invoice_template_candidate.xlsx
```

The default matching template contract is:

```text
C:\Users\IgorN\Downloads\client_style_template_phase_2_30e\client_style_invoice_template_contract.candidate.json
```

Override them only when a separately approved template and matching contract
are available. The default Python executable is:

```text
.\.venv\Scripts\python.exe
```

## Example command

Run from the repository root:

```powershell
.\scripts\run_client_style_invoice_export.ps1 `
  -CommercialCsv "C:\outside-git\approved-commercial.csv" `
  -InternalDraftXlsx "C:\outside-git\internal-draft.xlsx" `
  -ApprovalJson "C:\outside-git\client-style-approval.json" `
  -OutputXlsx "C:\outside-git\client-style-candidate.xlsx"
```

The launcher prints its operator safety header and the full exporter report.
It returns the exporter exit code unchanged.

## Operator decision after the run

An exporter exit code of `0` and report status `PASS` mean only that automated
checks passed. They do not approve commercial terms and do not authorize
sending.

Before any sending action:

1. Open the XLSX candidate and complete the manual Igor check.
2. Obtain a separate Human Approval.
3. Keep the output and every workflow input outside Git.

Generated XLSX, CSV and approval JSON files must not be committed. The
launcher does not call Git and does not send files.
