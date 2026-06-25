[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Python = "",

    [Parameter(Mandatory = $false)]
    [switch]$CopyToClipboard
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}

$FinishChecksScript = Join-Path $ProjectRoot "scripts\run_codex_finish_checks.py"

Push-Location $ProjectRoot
try {
    $FinishOutput = & $Python $FinishChecksScript --mode fast --include-quote-smoke 2>&1
    $FinishExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

$FinishLines = @($FinishOutput | ForEach-Object { [string]$_ })
$FinishLines | ForEach-Object { Write-Output $_ }

if ($CopyToClipboard) {
    $FinishText = $FinishLines -join [System.Environment]::NewLine
    try {
        Set-Clipboard -Value $FinishText
    }
    catch {
        Write-Warning "Could not copy finish output to clipboard."
    }
}

exit $FinishExitCode
