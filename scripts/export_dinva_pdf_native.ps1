throw 'DIRECT_NATIVE_PDF_EXPORT_CLOSED_USE_GOVERNED_EXPORTER'
param([Parameter(Mandatory=$true)][string]$Workbook,
      [Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference = 'Stop'
if ([IO.Path]::GetExtension($Workbook) -ne '.xlsx' -or
    [IO.Path]::GetExtension($Output) -ne '.pdf' -or
    -not [IO.File]::Exists($Workbook) -or [IO.File]::Exists($Output)) {
    throw 'Native PDF input/output collision or suffix failure'
}
$wu4Excel = $null
$wu4Book = $null
try {
    $wu4Excel = New-Object -ComObject Excel.Application
    $wu4Excel.Visible = $false
    $wu4Excel.DisplayAlerts = $false
    $wu4Excel.EnableEvents = $false
    $wu4Excel.AskToUpdateLinks = $false
    $wu4Excel.AutomationSecurity = 3
    $wu4Book = $wu4Excel.Workbooks.Open($Workbook, 0, $true)
    if (-not $wu4Book.ReadOnly -or $wu4Book.Worksheets.Count -ne 1) {
        throw 'Native PDF requires read-only single-sheet validated workbook'
    }
    $wu4Book.Worksheets.Item(1).Calculate()
    $wu4Pages = $wu4Book.Worksheets.Item(1).PageSetup.Pages.Count
    if ($wu4Pages -lt 1) { throw 'Native page count unavailable' }
    $wu4Book.ExportAsFixedFormat(0, $Output, 0, $true, $false)
    @{page_count=[int]$wu4Pages; engine='MICROSOFT_EXCEL'; version=$wu4Excel.Version} |
        ConvertTo-Json -Compress
} finally {
    if ($null -ne $wu4Book) {
        $wu4Book.Close($false)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($wu4Book)
    }
    if ($null -ne $wu4Excel) {
        $wu4Excel.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($wu4Excel)
    }
}
