[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Assert-LastCommand {
    param([Parameter(Mandatory = $true)][string]$Message)
    if ($LASTEXITCODE -ne 0) {
        throw "$Message (code $LASTEXITCODE)."
    }
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $repo ".env"
if (-not (Test-Path $envFile)) {
    throw ".env est requis; executer d'abord .\scripts\bootstrap_env.ps1."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop et la commande docker sont requis."
}

$projectLine = Get-Content $envFile | Where-Object { $_ -match "^COMPOSE_PROJECT_NAME=" } | Select-Object -Last 1
$project = if ($projectLine) { ($projectLine -split "=", 2)[1].Trim() } else { "csrs" }
if (-not $project) {
    $project = "csrs"
}

$previousLocation = Get-Location
try {
    Set-Location $repo
    & docker compose -p $project -f compose.yml up -d --build
    Assert-LastCommand "La construction de la stack a echoue"
    & docker compose -p $project -f compose.yml exec -T web python manage.py check --deploy
    Assert-LastCommand "Le controle Django a echoue"
    & docker compose -p $project -f compose.yml ps
    Assert-LastCommand "La lecture de l'etat Compose a echoue"
}
finally {
    Set-Location $previousLocation
}
