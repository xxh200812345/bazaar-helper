param(
    [string]$ManifestUrl = $env:BAZAAR_HELPER_UPDATE_MANIFEST_URL,
    [switch]$Force,
    [switch]$CheckOnly,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LocalAppData = $env:LOCALAPPDATA
if (-not $LocalAppData) {
    $LocalAppData = Join-Path $env:USERPROFILE "AppData\Local"
}
$StateRoot = Join-Path $LocalAppData "BazaarHelper"
$UpdateRoot = Join-Path $StateRoot "updates"
$BackupRoot = Join-Path $StateRoot "backups"
$LogPath = Join-Path $StateRoot "update.log"

if (-not $ManifestUrl) {
    $manifestUrlPath = Join-Path $AppRoot "update_url.txt"
    if (Test-Path $manifestUrlPath) {
        $ManifestUrl = (Get-Content -LiteralPath $manifestUrlPath -Raw -Encoding UTF8).Trim()
    }
}

function Write-UpdateLog {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    try {
        New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null
        Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
    } catch {
        if (-not $Quiet) {
            Write-Host "Unable to write update log: $($_.Exception.Message)"
        }
    }
    if (-not $Quiet) {
        Write-Host $Message
    }
}

function Read-LocalVersion {
    $jsonPath = Join-Path $AppRoot "version.json"
    if (Test-Path $jsonPath) {
        $versionInfo = Get-Content -LiteralPath $jsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($versionInfo.version) {
            return [string]$versionInfo.version
        }
    }

    $textPath = Join-Path $AppRoot "VERSION"
    if (Test-Path $textPath) {
        return (Get-Content -LiteralPath $textPath -Raw -Encoding UTF8).Trim()
    }

    return "0.0.0"
}

function Convert-ToVersion {
    param([string]$Value)
    $clean = ($Value -replace "^[vV]", "").Trim()
    try {
        return [version]$clean
    } catch {
        throw "Invalid version value: $Value"
    }
}

function Get-PayloadRoot {
    param([string]$ExtractRoot)
    if (Test-Path (Join-Path $ExtractRoot "BazaarHelper.exe")) {
        return $ExtractRoot
    }

    $children = Get-ChildItem -LiteralPath $ExtractRoot -Directory
    foreach ($child in $children) {
        if (Test-Path (Join-Path $child.FullName "BazaarHelper.exe")) {
            return $child.FullName
        }
    }

    throw "Downloaded package does not contain BazaarHelper.exe"
}

function Copy-Payload {
    param(
        [string]$SourceRoot,
        [string]$DestinationRoot
    )
    Get-ChildItem -LiteralPath $SourceRoot -Force | ForEach-Object {
        $destination = Join-Path $DestinationRoot $_.Name
        Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force
    }
}

if (-not $ManifestUrl) {
    Write-UpdateLog "Update manifest URL is not configured; skipping update check."
    exit 0
}

New-Item -ItemType Directory -Path $UpdateRoot -Force | Out-Null
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null

$currentVersionText = Read-LocalVersion
Write-UpdateLog "Current version: $currentVersionText"

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {
    Write-UpdateLog "Unable to force TLS 1.2: $($_.Exception.Message)"
}

$manifestPath = Join-Path $UpdateRoot "latest.json"
Write-UpdateLog "Checking update manifest: $ManifestUrl"
Invoke-WebRequest -Uri $ManifestUrl -OutFile $manifestPath -UseBasicParsing
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

if (-not $manifest.version -or -not $manifest.url -or -not $manifest.sha256) {
    throw "Update manifest must include version, url, and sha256."
}

$currentVersion = Convert-ToVersion $currentVersionText
$remoteVersion = Convert-ToVersion ([string]$manifest.version)
if (-not $Force -and $remoteVersion -le $currentVersion) {
    Write-UpdateLog "No update available. Latest version: $($manifest.version)"
    exit 0
}

if ($CheckOnly) {
    Write-UpdateLog "Update available: $currentVersionText -> $($manifest.version)"
    exit 2
}

$packagePath = Join-Path $UpdateRoot ("BazaarHelper-{0}.zip" -f $manifest.version)
$extractRoot = Join-Path $UpdateRoot ("extract-{0}" -f $manifest.version)
if (Test-Path $extractRoot) {
    Remove-Item -LiteralPath $extractRoot -Recurse -Force
}

Write-UpdateLog "Downloading update package: $($manifest.url)"
Invoke-WebRequest -Uri $manifest.url -OutFile $packagePath -UseBasicParsing

$actualHash = (Get-FileHash -LiteralPath $packagePath -Algorithm SHA256).Hash.ToLowerInvariant()
$expectedHash = ([string]$manifest.sha256).ToLowerInvariant()
if ($actualHash -ne $expectedHash) {
    throw "SHA256 mismatch. Expected $expectedHash, got $actualHash."
}
Write-UpdateLog "Package hash verified."

Expand-Archive -LiteralPath $packagePath -DestinationPath $extractRoot -Force
$payloadRoot = Get-PayloadRoot $extractRoot

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $BackupRoot ("BazaarHelper-{0}-{1}" -f $currentVersionText, $timestamp)
Write-UpdateLog "Creating backup: $backupPath"
New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
Copy-Payload $AppRoot $backupPath

Write-UpdateLog "Stopping running BazaarHelper.exe processes."
Get-Process -Name "BazaarHelper" -ErrorAction SilentlyContinue | Stop-Process -Force

try {
    Write-UpdateLog "Installing update version $($manifest.version)."
    Copy-Payload $payloadRoot $AppRoot
    Write-UpdateLog "Update complete: $currentVersionText -> $($manifest.version)"
    exit 0
} catch {
    Write-UpdateLog "Update failed, attempting rollback: $($_.Exception.Message)"
    Copy-Payload $backupPath $AppRoot
    throw
}
