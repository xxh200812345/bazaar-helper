param(
    [string]$ReleaseRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "release\BazaarHelper"),
    [string]$OutputRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "releases"),
    [string]$DownloadBaseUrl = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ReleaseRoot)) {
    throw "Release folder not found: $ReleaseRoot"
}

$versionPath = Join-Path $ReleaseRoot "version.json"
if (Test-Path $versionPath) {
    $versionInfo = Get-Content -LiteralPath $versionPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $version = [string]$versionInfo.version
} else {
    $version = (Get-Content -LiteralPath (Join-Path $ReleaseRoot "VERSION") -Raw -Encoding UTF8).Trim()
}

if (-not $version) {
    throw "Unable to determine release version."
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

$zipName = "BazaarHelper-$version.zip"
$zipPath = Join-Path $OutputRoot $zipName
if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

Compress-Archive -Path (Join-Path $ReleaseRoot "*") -DestinationPath $zipPath -Force
$sha256 = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()

if ($DownloadBaseUrl) {
    $base = $DownloadBaseUrl.TrimEnd("/")
    $downloadUrl = "$base/$zipName"
} else {
    $downloadUrl = $zipName
}

$manifest = [ordered]@{
    name = "BazaarHelper"
    version = $version
    url = $downloadUrl
    sha256 = $sha256
    notes = ""
    published_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
}

$manifestPath = Join-Path $OutputRoot "latest.json"
$manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "Update package created:" -ForegroundColor Green
Write-Host $zipPath
Write-Host "Manifest:"
Write-Host $manifestPath
