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

function Get-PreflightStatus {
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

$PreflightOutput = & $Python $PreflightScript --input $ItemsCsv --draft-output $Output 2>&1
$PreflightExitCode = $LASTEXITCODE
$PreflightLines = @($PreflightOutput | ForEach-Object { [string]$_ })
$PreflightLines | ForEach-Object { Write-Host $_ }

$PreflightStatus = Get-PreflightStatus -ReportLines $PreflightLines
$GenerationStatus = "skipped"
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
    $LauncherArgs = @($ItemsCsv, $Output)
    if (-not [string]::IsNullOrWhiteSpace($Template)) {
        $LauncherArgs += @("-Template", $Template)
    }
    $LauncherArgs += @("-TemplateCapacity", $TemplateCapacity)
    $LauncherArgs += @("-Python", $Python)

    & $LauncherScript @LauncherArgs
    $GeneratorExitCode = $LASTEXITCODE

    if ($GeneratorExitCode -eq 0 -and (Test-Path -LiteralPath $Output -PathType Leaf)) {
        $GenerationStatus = "pass"
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
    -OutputExists $OutputExists `
    -NextMessage $NextMessage

exit $FinalExitCode
