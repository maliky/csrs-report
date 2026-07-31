[CmdletBinding()]
param(
    [string]$HostName = $(if ($env:CSRS_HOST) { $env:CSRS_HOST } else { "localhost" }),
    [string]$BindAddress = $(if ($env:CSRS_BIND_ADDRESS) { $env:CSRS_BIND_ADDRESS } else { "127.0.0.1" }),
    [int]$Port = $(if ($env:CSRS_PORT) { [int]$env:CSRS_PORT } else { 8000 }),
    [string]$ProjectName = $(if ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { "csrs" })
)

$ErrorActionPreference = "Stop"

function New-UrlSafeSecret {
    param([Parameter(Mandatory = $true)][int]$ByteCount)

    $bytes = New-Object byte[] $ByteCount
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $repo ".env"
if (Test-Path $envFile) {
    Write-Host ".env existe deja; aucun secret n'a ete remplace."
    exit 0
}

$secretKey = New-UrlSafeSecret -ByteCount 50
$dbPassword = New-UrlSafeSecret -ByteCount 32
$trustedOrigins = @(
    "http://localhost:$Port"
    "http://127.0.0.1:$Port"
    "http://localhost:5173"
    "http://127.0.0.1:5173"
) -join ","

$lines = @(
    "COMPOSE_PROJECT_NAME=$ProjectName"
    "CSRS_BIND_ADDRESS=$BindAddress"
    "CSRS_PORT=$Port"
    "CSRS_HOST=$HostName"
    "DJANGO_SECRET_KEY=$secretKey"
    "DJANGO_DEBUG=1"
    "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,$HostName"
    "DJANGO_CSRF_TRUSTED_ORIGINS=$trustedOrigins"
    "DJANGO_SECURE_SSL_REDIRECT=0"
    "DJANGO_SECURE_HSTS_SECONDS=0"
    "OBSERVABLE_EXPORT_TOKEN_MAX_AGE_SECONDS=900"
    "DATABASE_URL=postgresql://csrs:${dbPassword}@db:5432/csrs"
    "POSTGRES_DB=csrs"
    "POSTGRES_USER=csrs"
    "POSTGRES_PASSWORD=$dbPassword"
    "EMAIL_HOST=mail.koba.sarl"
    "EMAIL_PORT=587"
    "EMAIL_HOST_USER="
    "EMAIL_HOST_PASSWORD="
    "EMAIL_USE_TLS=1"
    "DEFAULT_FROM_EMAIL=CSRS Report <noreply@koba.sarl>"
)

$utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText(
    $envFile,
    ($lines -join [Environment]::NewLine) + [Environment]::NewLine,
    $utf8WithoutBom
)

Write-Host ".env local cree avec des secrets aleatoires et les origines Vite autorisees."
