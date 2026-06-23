[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Get-ReportValue {
    param(
        [string[]]$ReportLines,
        [string]$Label
    )

    for ($Index = 0; $Index -lt $ReportLines.Count; $Index++) {
        if ($ReportLines[$Index] -eq $Label) {
            for ($ValueIndex = $Index + 1; $ValueIndex -lt $ReportLines.Count; $ValueIndex++) {
                $Candidate = $ReportLines[$ValueIndex].Trim()
                if (-not [string]::IsNullOrWhiteSpace($Candidate)) {
                    return $Candidate
                }
            }
        }
    }

    return ""
}

function Convert-ExpectedStatus {
    param(
        [string]$Value,
        [string]$ExpectedValue,
        [string]$UnexpectedValue
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "missing"
    }
    if ($Value -eq $ExpectedValue) {
        return $ExpectedValue
    }
    return $UnexpectedValue
}

function Write-SmokeReport {
    param(
        [string]$CheckedLauncherStatus,
        [bool]$HasPreflightReport,
        [string]$PreflightStatus,
        [bool]$HasDraftInspectionReport,
        [string]$InspectionStatus,
        [bool]$HasCheckedRunReport,
        [string]$GenerationStatus,
        [string]$OutputExistsInCheckedReport,
        [bool]$OutputCreated,
        [bool]$TempCsvDeleted,
        [bool]$TempXlsxDeleted,
        [string]$Result
    )

    $OutputCreatedText = if ($OutputCreated) { "yes" } else { "no" }
    $TempCsvDeletedText = if ($TempCsvDeleted) { "yes" } else { "no" }
    $TempXlsxDeletedText = if ($TempXlsxDeleted) { "yes" } else { "no" }
    $HasPreflightReportText = if ($HasPreflightReport) { "yes" } else { "no" }
    $HasDraftInspectionReportText = if ($HasDraftInspectionReport) { "yes" } else { "no" }
    $HasCheckedRunReportText = if ($HasCheckedRunReport) { "yes" } else { "no" }

    Write-Host "CHECKED_QUOTE_SMOKE_REPORT_START"
    Write-Host ""
    Write-Host "Mode:"
    Write-Host $Result
    Write-Host ""
    Write-Host "Checked launcher:"
    Write-Host $CheckedLauncherStatus
    Write-Host ""
    Write-Host "Preflight report:"
    Write-Host $HasPreflightReportText
    Write-Host ""
    Write-Host "Preflight status:"
    Write-Host $PreflightStatus
    Write-Host ""
    Write-Host "Draft inspection report:"
    Write-Host $HasDraftInspectionReportText
    Write-Host ""
    Write-Host "Inspection:"
    Write-Host $InspectionStatus
    Write-Host ""
    Write-Host "Checked run report:"
    Write-Host $HasCheckedRunReportText
    Write-Host ""
    Write-Host "Generation:"
    Write-Host $GenerationStatus
    Write-Host ""
    Write-Host "Output exists in checked report:"
    Write-Host $OutputExistsInCheckedReport
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
$HasPreflightReport = $false
$PreflightStatus = "missing"
$HasDraftInspectionReport = $false
$InspectionStatus = "missing"
$HasCheckedRunReport = $false
$GenerationStatus = "missing"
$OutputExistsInCheckedReport = "missing"
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
    $HasPreflightReport = $LauncherLines -contains "QUOTE_INPUT_PREFLIGHT_REPORT_START"
    $HasDraftInspectionReport = $LauncherLines -contains "QUOTE_DRAFT_INSPECTION_REPORT_START"
    $HasCheckedRunReport = $LauncherLines -contains "CHECKED_QUOTE_RUN_REPORT_START"
    $PreflightValue = Get-ReportValue -ReportLines $LauncherLines -Label "Preflight:"
    $GenerationValue = Get-ReportValue -ReportLines $LauncherLines -Label "Generation:"
    $InspectionValue = Get-ReportValue -ReportLines $LauncherLines -Label "Inspection:"
    $OutputExistsValue = Get-ReportValue -ReportLines $LauncherLines -Label "Output exists:"
    $PreflightStatus = Convert-ExpectedStatus `
        -Value $PreflightValue `
        -ExpectedValue "PASS" `
        -UnexpectedValue "unexpected"
    $GenerationStatus = Convert-ExpectedStatus `
        -Value $GenerationValue `
        -ExpectedValue "pass" `
        -UnexpectedValue "fail"
    $InspectionStatus = Convert-ExpectedStatus `
        -Value $InspectionValue `
        -ExpectedValue "pass" `
        -UnexpectedValue "fail"
    $OutputExistsInCheckedReport = Convert-ExpectedStatus `
        -Value $OutputExistsValue `
        -ExpectedValue "yes" `
        -UnexpectedValue "no"

    if (
        $LauncherExitCode -eq 0 -and
        $OutputCreated -and
        $HasPreflightReport -and
        $PreflightStatus -eq "PASS" -and
        $HasDraftInspectionReport -and
        $InspectionStatus -eq "pass" -and
        $HasCheckedRunReport -and
        $GenerationStatus -eq "pass" -and
        $OutputExistsInCheckedReport -eq "yes"
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
        -HasPreflightReport $HasPreflightReport `
        -PreflightStatus $PreflightStatus `
        -HasDraftInspectionReport $HasDraftInspectionReport `
        -InspectionStatus $InspectionStatus `
        -HasCheckedRunReport $HasCheckedRunReport `
        -GenerationStatus $GenerationStatus `
        -OutputExistsInCheckedReport $OutputExistsInCheckedReport `
        -OutputCreated $OutputCreated `
        -TempCsvDeleted $TempCsvDeleted `
        -TempXlsxDeleted $TempXlsxDeleted `
        -Result $Result
}

exit $ExitCode
