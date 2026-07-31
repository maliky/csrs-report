[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $line = Get-Content $Path | Where-Object { $_ -match "^$([Regex]::Escape($Name))=" } | Select-Object -Last 1
    if (-not $line) {
        return $null
    }
    return ($line -split "=", 2)[1].Trim()
}

function Assert-LastCommand {
    param([Parameter(Mandatory = $true)][string]$Message)
    if ($LASTEXITCODE -ne 0) {
        throw "$Message (code $LASTEXITCODE)."
    }
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $repo ".env"
if (-not (Test-Path $envFile)) {
    throw ".env est requis pour identifier la base CSRS."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop et la commande docker sont requis."
}

$database = Get-EnvValue -Path $envFile -Name "POSTGRES_DB"
$databaseUser = Get-EnvValue -Path $envFile -Name "POSTGRES_USER"
$project = Get-EnvValue -Path $envFile -Name "COMPOSE_PROJECT_NAME"
if (-not $database -or -not $databaseUser) {
    throw "POSTGRES_DB et POSTGRES_USER sont requis dans .env."
}
if (-not $project) {
    $project = "csrs"
}

$backupDirectory = Join-Path $repo "backups"
New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
$timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$fileName = "csrs_$timestamp.dump"
$output = Join-Path $backupDirectory $fileName
$containerBackup = "/tmp/$fileName"
$previousLocation = Get-Location

try {
    Set-Location $repo
    $containerId = (& docker compose -p $project -f compose.yml ps -q db | Select-Object -First 1)
    Assert-LastCommand "Impossible d'identifier le conteneur PostgreSQL"
    if (-not $containerId) {
        throw "Le conteneur PostgreSQL n'est pas demarre."
    }
    $containerId = $containerId.Trim()

    & docker compose -p $project -f compose.yml exec -T db pg_dump --format=custom --no-owner --username $databaseUser --file $containerBackup $database
    Assert-LastCommand "pg_dump a echoue"

    & docker cp "${containerId}:${containerBackup}" $output
    Assert-LastCommand "La copie de la sauvegarde a echoue"

    & docker compose -p $project -f compose.yml exec -T db pg_restore --list $containerBackup | Out-Null
    Assert-LastCommand "La validation de la sauvegarde a echoue"
}
finally {
    if ($containerId) {
        & docker compose -p $project -f compose.yml exec -T db rm -f $containerBackup 2>$null | Out-Null
    }
    Set-Location $previousLocation
}

$retentionLimit = [DateTime]::UtcNow.AddDays(-14)
Get-ChildItem $backupDirectory -Filter "csrs_*.dump" -File |
    Where-Object { $_.LastWriteTimeUtc -lt $retentionLimit } |
    Remove-Item -Force

Write-Host "Sauvegarde verifiee : $output"
