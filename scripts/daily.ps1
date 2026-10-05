param(
    [switch]$SkipCollect,
    [ValidateRange(1, 365)][int]$Days = 7,
    [ValidateRange(1, 365)][int]$EndingDays = 7,
    [ValidateRange(1, 500)][int]$Limit = 20,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$reportDirectory = Join-Path $projectRoot "reports"

Push-Location $projectRoot
try {
    if (-not $SkipCollect) {
        & $Python main.py collect
        if ($LASTEXITCODE -ne 0) {
            throw "collection failed with exit code $LASTEXITCODE"
        }
    }

    New-Item -ItemType Directory -Force -Path $reportDirectory | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $reportPath = Join-Path $reportDirectory "digest-$stamp.md"
    $digest = & $Python main.py digest --days $Days --ending-days $EndingDays --limit $Limit
    if ($LASTEXITCODE -ne 0) {
        throw "digest failed with exit code $LASTEXITCODE"
    }
    @(
        "# Pokemon Event Digest"
        ""
        "Generated at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
        ""
        $digest
    ) | Set-Content -LiteralPath $reportPath -Encoding utf8
    Write-Output "report=$reportPath"
}
finally {
    Pop-Location
}
