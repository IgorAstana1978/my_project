[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}

$FinishChecksScript = Join-Path $ProjectRoot "scripts\run_codex_finish_checks.py"

Push-Location $ProjectRoot
try {
    & $Python $FinishChecksScript --mode fast --include-quote-smoke
    $FinishExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $FinishExitCode
