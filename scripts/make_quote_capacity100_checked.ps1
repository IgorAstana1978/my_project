[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$ItemsCsv,

    [Parameter(Mandatory = $true, Position = 1)]
    [string]$Output,

    [Parameter(Mandatory = $false)]
    [string]$Template = "",

    [Parameter(Mandatory = $false)]
    [int]$TemplateCapacity = 100,

    [Parameter(Mandatory = $false)]
    [string]$Python = "",

    [Parameter(Mandatory = $false)]
    [switch]$AllowWarn
)

$ErrorActionPreference = "Stop"

function Get-ReportStatus {
    param([string[]]$ReportLines)

    for ($Index = 0; $Index -lt $ReportLines.Count; $Index++) {
        if ($ReportLines[$Index] -eq "Status:") {
            for ($ValueIndex = $Index + 1; $ValueIndex -lt $ReportLines.Count; $ValueIndex++) {
                $Candidate = $ReportLines[$ValueIndex].Trim()
                if (-not [string]::IsNullOrWhiteSpace($Candidate)) {
                    return $Candidate
                }
            }
        }
    }

    return "FAIL"
}

function Write-CheckedQuoteRunReport {
    param(
        [string]$PreflightStatus,
        [string]$GenerationStatus,
        [string]$InspectionStatus,
        [bool]$OutputExists,
        [string]$NextMessage
    )

    $OutputExistsText = if ($OutputExists) { "yes" } else { "no" }

    Write-Host "CHECKED_QUOTE_RUN_REPORT_START"
    Write-Host ""
    Write-Host "Input:"
    Write-Host $ItemsCsv
    Write-Host ""
    Write-Host "Output:"
    Write-Host $Output
    Write-Host ""
    Write-Host "Preflight:"
    Write-Host $PreflightStatus
    Write-Host ""
    Write-Host "Generation:"
    Write-Host $GenerationStatus
    Write-Host ""
    Write-Host "Inspection:"
    Write-Host $InspectionStatus
    Write-Host ""
    Write-Host "Output exists:"
    Write-Host $OutputExistsText
    Write-Host ""
    Write-Host "Next:"
    Write-Host $NextMessage
    Write-Host ""
    Write-Host "CHECKED_QUOTE_RUN_REPORT_END"
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}

$PreflightScript = Join-Path $ProjectRoot "scripts\preflight_quote_input.py"
$LauncherScript = Join-Path $ProjectRoot "scripts\make_quote_capacity100.ps1"
$InspectionScript = Join-Path $ProjectRoot "scripts\inspect_quote_draft.py"

$PreflightOutput = & $Python $PreflightScript --input $ItemsCsv --draft-output $Output 2>&1
$PreflightExitCode = $LASTEXITCODE
$PreflightLines = @($PreflightOutput | ForEach-Object { [string]$_ })
$PreflightLines | ForEach-Object { Write-Host $_ }

$PreflightStatus = Get-ReportStatus -ReportLines $PreflightLines
$GenerationStatus = "skipped"
$InspectionStatus = "skipped"
$NextMessage = "manual Igor check required before sending to client"
$FinalExitCode = 0

if ($PreflightExitCode -ne 0 -or $PreflightStatus -eq "FAIL") {
    $FinalExitCode = if ($PreflightExitCode -ne 0) { $PreflightExitCode } else { 1 }
}
elseif ($PreflightStatus -eq "WARN" -and -not $AllowWarn) {
    $NextMessage = "WARN requires manual Igor check and rerun with -AllowWarn"
    $FinalExitCode = 2
}
elseif ($PreflightStatus -eq "PASS" -or ($PreflightStatus -eq "WARN" -and $AllowWarn)) {
    $LauncherParams = @{
        ItemsCsv = $ItemsCsv
        Output = $Output
        TemplateCapacity = $TemplateCapacity
        Python = $Python
    }
    if (-not [string]::IsNullOrWhiteSpace($Template)) {
        $LauncherParams["Template"] = $Template
    }

    & $LauncherScript @LauncherParams
    $GeneratorExitCode = $LASTEXITCODE

    if ($GeneratorExitCode -eq 0 -and (Test-Path -LiteralPath $Output -PathType Leaf)) {
        $GenerationStatus = "pass"
        $InspectionOutput = & $Python $InspectionScript --input $Output 2>&1
        $InspectionExitCode = $LASTEXITCODE
        $InspectionLines = @($InspectionOutput | ForEach-Object { [string]$_ })
        $InspectionLines | ForEach-Object { Write-Host $_ }
        $DraftInspectionStatus = Get-ReportStatus -ReportLines $InspectionLines

        if ($InspectionExitCode -eq 0 -and $DraftInspectionStatus -eq "PASS") {
            $InspectionStatus = "pass"
        }
        else {
            $InspectionStatus = "fail"
            $NextMessage = "draft inspection failed; do not use draft"
            $FinalExitCode = if ($InspectionExitCode -ne 0) { $InspectionExitCode } else { 1 }
        }
    }
    else {
        $GenerationStatus = "fail"
        $FinalExitCode = if ($GeneratorExitCode -ne 0) { $GeneratorExitCode } else { 1 }
    }
}
else {
    $NextMessage = "preflight status is unknown; not safe to run"
    $FinalExitCode = 1
}

$OutputExists = Test-Path -LiteralPath $Output -PathType Leaf
Write-CheckedQuoteRunReport `
    -PreflightStatus $PreflightStatus `
    -GenerationStatus $GenerationStatus `
    -InspectionStatus $InspectionStatus `
    -OutputExists $OutputExists `
    -NextMessage $NextMessage

exit $FinalExitCode
