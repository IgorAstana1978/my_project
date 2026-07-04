[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CommercialCsv,

    [Parameter(Mandatory = $true)]
    [string]$InternalDraftXlsx,

    [Parameter(Mandatory = $true)]
    [string]$ApprovalJson,

    [Parameter(Mandatory = $true)]
    [string]$OutputXlsx,

    [Parameter(Mandatory = $false)]
    [string]$TemplateXlsx = "C:\Users\IgorN\Downloads\client_style_template_phase_2_30e\client_style_invoice_template_candidate.xlsx",

    [Parameter(Mandatory = $false)]
    [string]$TemplateContractJson = "C:\Users\IgorN\Downloads\client_style_template_phase_2_30e\client_style_invoice_template_contract.candidate.json",

    [Parameter(Mandatory = $false)]
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}

$Exporter = Join-Path $ProjectRoot "scripts\export_client_style_invoice.py"

Write-Host "client-style invoice export candidate only"
Write-Host "PASS is not sending approval"
Write-Host "Human Approval required before sending"

& $Python $Exporter `
    --commercial-csv $CommercialCsv `
    --internal-draft-xlsx $InternalDraftXlsx `
    --template-xlsx $TemplateXlsx `
    --template-contract-json $TemplateContractJson `
    --approval-json $ApprovalJson `
    --output-xlsx $OutputXlsx

$ExitCode = $LASTEXITCODE
exit $ExitCode
