[CmdletBinding()]
param(
    [switch]$DryRunOnly
)

$ErrorActionPreference = "Stop"

function Read-PlainTextSecret {
    param([Parameter(Mandatory = $true)][string]$Prompt)

    $secure = Read-Host $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Invoke-Seed {
    param([switch]$DryRun)

    $arguments = @(
        "compose", "-p", $script:project, "-f", "compose.yml",
        "run", "--rm", "-T",
        "-e", "CSRS_DEMO_PASSWORD",
        "-e", "CSRS_ADMIN_PASSWORD",
        "web", "python", "manage.py", "seed_pilot_users",
        "--replace-legacy", "--reset-password"
    )
    if ($DryRun) {
        $arguments += "--dry-run"
    }
    & docker @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Le chargement pilote a echoue (code $LASTEXITCODE)."
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
$script:project = if ($projectLine) { ($projectLine -split "=", 2)[1].Trim() } else { "csrs" }
if (-not $script:project) {
    $script:project = "csrs"
}

$previousLocation = Get-Location
try {
    Set-Location $repo
    if (-not $env:CSRS_DEMO_PASSWORD) {
        $env:CSRS_DEMO_PASSWORD = Read-PlainTextSecret "Mot de passe des comptes metier"
    }
    if (-not $env:CSRS_ADMIN_PASSWORD) {
        $env:CSRS_ADMIN_PASSWORD = Read-PlainTextSecret "Mot de passe du compte dev"
    }

    Invoke-Seed -DryRun
    if (-not $DryRunOnly) {
        Invoke-Seed
    }
}
finally {
    Remove-Item Env:CSRS_DEMO_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:CSRS_ADMIN_PASSWORD -ErrorAction SilentlyContinue
    Set-Location $previousLocation
}
