[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$CommercialCsv,

    [Parameter(Mandatory = $true, Position = 1)]
    [string]$Output,

    [Parameter(Mandatory = $false)]
    [string]$Template = (Join-Path (Join-Path $env:USERPROFILE "Downloads") ([regex]::Unescape("\u0424\u0438\u0440\u043c\u0435\u043d\u043d\u044b\u0439_\u0448\u0430\u0431\u043b\u043e\u043d_\u0441\u0447\u0451\u0442\u0430-\u041a\u041f_v0.3_capacity100_tuned_v3_\u0414\u0438\u041d_\u0412\u0410-\u041a\u042d\u0421.xlsx"))),

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

$Runner = Join-Path $ProjectRoot "scripts\run_invoice_quote_commercial_from_csv.py"
$OutputParent = Split-Path -Parent $Output

if (-not (Test-Path -LiteralPath $CommercialCsv -PathType Leaf)) {
    Stop-WithMessage "Commercial CSV does not exist: $CommercialCsv"
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

Write-Host "Creating capacity100 internal commercial draft..."
Write-Host "Commercial CSV: $CommercialCsv"
Write-Host "Output: $Output"

& $Python $Runner `
    --commercial-csv $CommercialCsv `
    --template $Template `
    --template-capacity 100 `
    --output $Output

$ExitCode = $LASTEXITCODE
if ($ExitCode -ne 0) {
    exit $ExitCode
}

Write-Host "Created internal draft: $Output"
exit 0
