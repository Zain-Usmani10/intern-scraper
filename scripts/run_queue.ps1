# Adds every batch in data/queue.txt, one line at a time, without asking.
# Companies that pass are added. needs_approval ones are recorded for review.
# A failed batch (for example, the internet dropped) is retried 3 times.
# Output goes to data/tmp/queue_log.txt.
#
# Usage, from the project folder:
#     powershell -ExecutionPolicy Bypass -File scripts\run_queue.ps1

Set-Location (Split-Path $PSScriptRoot)
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"
$log = "data\tmp\queue_log.txt"

# Show each line in the terminal and save it to the log.
function Show($line) {
    Write-Host $line
    "$line" | Out-File $log -Append -Encoding utf8
}

foreach ($batch in Get-Content "data\queue.txt") {
    if (-not $batch.Trim()) { continue }
    for ($try = 1; $try -le 3; $try++) {
        Show "`n##### $(Get-Date -Format 'HH:mm') $batch (try $try)"
        & .venv\Scripts\python scripts\add_company.py --yes $batch 2>&1 | ForEach-Object { Show "$_" }
        if ($LASTEXITCODE -eq 0) { break }
        Show "##### Failed. Retrying in 2 minutes."
        Start-Sleep -Seconds 120
    }
}
Show "`n##### $(Get-Date -Format 'HH:mm') Queue finished."
