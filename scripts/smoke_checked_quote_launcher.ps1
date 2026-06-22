[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Test-ReportPair {
    param(
        [string[]]$ReportLines,
        [string]$Label,
        [string]$ExpectedValue
    )

    for ($Index = 0; $Index -lt $ReportLines.Count; $Index++) {
        if ($ReportLines[$Index] -eq $Label) {
            for ($ValueIndex = $Index + 1; $ValueIndex -lt $ReportLines.Count; $ValueIndex++) {
                $Candidate = $ReportLines[$ValueIndex].Trim()
                if (-not [string]::IsNullOrWhiteSpace($Candidate)) {
                    return $Candidate -eq $ExpectedValue
                }
            }
        }
    }

    return $false
}

function Write-SmokeReport {
    param(
        [string]$CheckedLauncherStatus,
        [bool]$OutputCreated,
        [bool]$TempCsvDeleted,
        [bool]$TempXlsxDeleted,
        [string]$Result
    )

    $OutputCreatedText = if ($OutputCreated) { "yes" } else { "no" }
    $TempCsvDeletedText = if ($TempCsvDeleted) { "yes" } else { "no" }
    $TempXlsxDeletedText = if ($TempXlsxDeleted) { "yes" } else { "no" }

    Write-Host "CHECKED_QUOTE_SMOKE_REPORT_START"
    Write-Host ""
    Write-Host "Mode:"
    Write-Host "PASS"
    Write-Host ""
    Write-Host "Checked launcher:"
    Write-Host $CheckedLauncherStatus
    Write-Host ""
    Write-Host "Output created:"
    Write-Host $OutputCreatedText
    Write-Host ""
    Write-Host "Temp CSV deleted:"
    Write-Host $TempCsvDeletedText
    Write-Host ""
    Write-Host "Temp XLSX deleted:"
    Write-Host $TempXlsxDeletedText
    Write-Host ""
    Write-Host "Result:"
    Write-Host $Result
    Write-Host ""
    Write-Host "CHECKED_QUOTE_SMOKE_REPORT_END"
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CheckedLauncher = Join-Path $ProjectRoot "scripts\make_quote_capacity100_checked.ps1"
$TempRoot = [System.IO.Path]::GetFullPath($env:TEMP)
$SmokeId = [guid]::NewGuid().ToString("N")
$TempCsv = [System.IO.Path]::GetFullPath((Join-Path $TempRoot "codex_checked_quote_smoke_$SmokeId.csv"))
$TempXlsx = [System.IO.Path]::GetFullPath((Join-Path $TempRoot "codex_checked_quote_smoke_$SmokeId.xlsx"))
$SyntheticCsv = "name;unit;quantity;instruments_and_devices;cabinet_type_dimensions_material`n" +
    "ВРУ-SMOKE-1;шт.;1;synthetic devices;synthetic cabinet`n" +
    "ВРУ-SMOKE-2;шт.;2;synthetic devices;synthetic cabinet`n"

$CheckedLauncherStatus = "fail"
$OutputCreated = $false
$TempCsvDeleted = $false
$TempXlsxDeleted = $false
$Result = "FAIL"
$ExitCode = 1

try {
    if (-not $TempCsv.StartsWith($TempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "temp CSV path escaped TEMP"
    }
    if (-not $TempXlsx.StartsWith($TempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "temp XLSX path escaped TEMP"
    }
    if (Test-Path -LiteralPath $TempCsv) {
        throw "temp CSV already exists"
    }
    if (Test-Path -LiteralPath $TempXlsx) {
        throw "temp XLSX already exists"
    }

    [System.IO.File]::WriteAllText($TempCsv, $SyntheticCsv, [System.Text.UTF8Encoding]::new($false))

    $LauncherOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File $CheckedLauncher $TempCsv $TempXlsx 2>&1
    $LauncherExitCode = $LASTEXITCODE
    $LauncherLines = @($LauncherOutput | ForEach-Object { [string]$_ })
    $LauncherLines | ForEach-Object { Write-Host $_ }

    $OutputCreated = Test-Path -LiteralPath $TempXlsx -PathType Leaf
    $HasRunReport = $LauncherLines -contains "CHECKED_QUOTE_RUN_REPORT_START"
    $PreflightPass = Test-ReportPair -ReportLines $LauncherLines -Label "Preflight:" -ExpectedValue "PASS"
    $GenerationPass = Test-ReportPair -ReportLines $LauncherLines -Label "Generation:" -ExpectedValue "pass"
    $OutputExistsYes = Test-ReportPair -ReportLines $LauncherLines -Label "Output exists:" -ExpectedValue "yes"

    if (
        $LauncherExitCode -eq 0 -and
        $OutputCreated -and
        $HasRunReport -and
        $PreflightPass -and
        $GenerationPass -and
        $OutputExistsYes
    ) {
        $CheckedLauncherStatus = "pass"
        $Result = "PASS"
        $ExitCode = 0
    }
}
finally {
    if (Test-Path -LiteralPath $TempCsv) {
        Remove-Item -LiteralPath $TempCsv -Force
    }
    if (Test-Path -LiteralPath $TempXlsx) {
        Remove-Item -LiteralPath $TempXlsx -Force
    }
    $TempCsvDeleted = -not (Test-Path -LiteralPath $TempCsv)
    $TempXlsxDeleted = -not (Test-Path -LiteralPath $TempXlsx)

    if (-not $TempCsvDeleted -or -not $TempXlsxDeleted) {
        $Result = "FAIL"
        $ExitCode = 1
    }

    Write-SmokeReport `
        -CheckedLauncherStatus $CheckedLauncherStatus `
        -OutputCreated $OutputCreated `
        -TempCsvDeleted $TempCsvDeleted `
        -TempXlsxDeleted $TempXlsxDeleted `
        -Result $Result
}

exit $ExitCode
