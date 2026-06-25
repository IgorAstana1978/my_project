[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$CopyToClipboard
)

$ErrorActionPreference = "Stop"

$StateCard = @'
QUOTE_WORKFLOW_STATE_START

Repo:
invoice_quote_filler v0.2.1

Generate draft:
.\scripts\make_quote_capacity100_checked.ps1 "<strict_csv_outside_git>" "<draft_xlsx_outside_git>"

Finish / handoff:
.\scripts\finish_quote_workflow.ps1

Finish / handoff to clipboard:
.\scripts\finish_quote_workflow.ps1 -CopyToClipboard

State card to clipboard:
.\scripts\quote_workflow_state.ps1 -CopyToClipboard

Input:
strict 5-column CSV outside Git only

Output:
generated .xlsx is internal draft only and must stay outside Git

Stop before client:
manual Igor check and separate Human Approval required before sending to client

Safety:
technical PASS / smoke PASS is not commercial approval
no purchase/workshop/shipment/client sending from scripts

QUOTE_WORKFLOW_STATE_END
'@

Write-Output $StateCard

if ($CopyToClipboard) {
    Set-Clipboard -Value $StateCard
}
