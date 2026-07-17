[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InternalDraftXlsx,

    [Parameter(Mandatory = $true)]
    [string]$ApprovalJson,

    [Parameter(Mandatory = $true)]
    [string]$OutputXlsx,

    [Parameter(Mandatory = $false)]
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}

$Transformer = Join-Path $ProjectRoot "scripts\checked_clientize_quote.py"

Write-Host "checked multi-item client XLSX candidate only"
Write-Host "PASS is not sending approval"
Write-Host "No PDF, calculator, procurement, production or sending action"

& $Python $Transformer `
    --internal-draft-xlsx $InternalDraftXlsx `
    --approval-json $ApprovalJson `
    --output-xlsx $OutputXlsx

$ExitCode = $LASTEXITCODE
exit $ExitCode
