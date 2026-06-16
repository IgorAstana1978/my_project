[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$ItemsCsv,

    [Parameter(Mandatory = $true, Position = 1)]
    [string]$Output,

    [Parameter(Mandatory = $false)]
    [string]$Template = (Join-Path $env:USERPROFILE "Downloads\Фирменный_шаблон_счёта-КП_v0.3_capacity100_tuned_v3_ДиН_ВА-КЭС.xlsx"),

    [Parameter(Mandatory = $false)]
    [int]$TemplateCapacity = 100,

    [Parameter(Mandatory = $false)]
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

function Stop-WithMessage {
    param([string]$Message)
    Write-Error $Message
    exit 1
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}

$Runner = Join-Path $ProjectRoot "scripts\run_invoice_quote_extended_from_csv_compact.py"
$OutputParent = Split-Path -Parent $Output

if (-not (Test-Path -LiteralPath $ItemsCsv -PathType Leaf)) {
    Stop-WithMessage "Input CSV does not exist: $ItemsCsv"
}

if (-not (Test-Path -LiteralPath $Template -PathType Leaf)) {
    Stop-WithMessage "Template does not exist: $Template"
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    Stop-WithMessage "Python executable does not exist: $Python"
}

if (Test-Path -LiteralPath $Output) {
    Stop-WithMessage "Output already exists: $Output"
}

if ([string]::IsNullOrWhiteSpace($OutputParent)) {
    $OutputParent = (Get-Location).Path
}

if (-not (Test-Path -LiteralPath $OutputParent -PathType Container)) {
    Stop-WithMessage "Output parent directory does not exist: $OutputParent"
}

Write-Host "Creating capacity100 draft..."
Write-Host "Input CSV: $ItemsCsv"
Write-Host "Output: $Output"

& $Python $Runner `
    --items-csv $ItemsCsv `
    --template $Template `
    --template-capacity $TemplateCapacity `
    --output $Output

$ExitCode = $LASTEXITCODE
if ($ExitCode -ne 0) {
    exit $ExitCode
}

Write-Host "Created output: $Output"
exit 0
