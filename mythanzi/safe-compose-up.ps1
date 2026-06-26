param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ComposeArgs
)

$ErrorActionPreference = "Stop"

function Read-DotEnvValue {
    param(
        [string]$Path,
        [string]$Name,
        [string]$Default = ""
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $Default
    }

    $line = Get-Content -LiteralPath $Path |
        Where-Object { $_ -match "^\s*$([regex]::Escape($Name))\s*=" } |
        Select-Object -First 1

    if (-not $line) {
        return $Default
    }

    return (($line -split "=", 2)[1]).Trim().Trim('"').Trim("'")
}

function Wait-ForPostgres {
    param(
        [string]$Service,
        [string]$User,
        [string]$Database
    )

    Write-Host "Waiting for $Service database readiness..."
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        docker compose exec -T $Service pg_isready -U $User -d $Database *> $null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 2
    }

    throw "$Service did not become ready in time."
}

function Backup-Postgres {
    param(
        [string]$Service,
        [string]$User,
        [string]$Database,
        [string]$Prefix,
        [string]$OutputPath
    )

    Write-Host "Backing up $Database from $Service to $OutputPath"
    docker compose exec -T $Service pg_dump -U $User -d $Database --format=plain --no-owner --no-privileges |
        Set-Content -LiteralPath $OutputPath

    if ($LASTEXITCODE -ne 0) {
        throw "Backup failed for $Service."
    }
}

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

$envPath = Join-Path $ProjectDir ".env"
$backupDir = Join-Path $ProjectDir "backups"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

$postgresDb = Read-DotEnvValue -Path $envPath -Name "POSTGRES_DB" -Default "mythanzi"
$postgresUser = Read-DotEnvValue -Path $envPath -Name "POSTGRES_USER" -Default "postgres"

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

Write-Host "Starting database containers for backup..."
docker compose up -d db hapi-db
if ($LASTEXITCODE -ne 0) {
    throw "Could not start database containers."
}

Wait-ForPostgres -Service "db" -User $postgresUser -Database $postgresDb
Wait-ForPostgres -Service "hapi-db" -User "hapi" -Database "hapi"

Backup-Postgres `
    -Service "db" `
    -User $postgresUser `
    -Database $postgresDb `
    -Prefix "mythanzi" `
    -OutputPath (Join-Path $backupDir "mythanzi-$timestamp.sql")

Backup-Postgres `
    -Service "hapi-db" `
    -User "hapi" `
    -Database "hapi" `
    -Prefix "hapi" `
    -OutputPath (Join-Path $backupDir "hapi-$timestamp.sql")

Get-ChildItem -LiteralPath $backupDir -Filter "*.sql" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
    Remove-Item -Force

if (-not $ComposeArgs -or $ComposeArgs.Count -eq 0) {
    $ComposeArgs = @("up", "-d")
}

Write-Host "Running: docker compose $($ComposeArgs -join ' ')"
docker compose @ComposeArgs
if ($LASTEXITCODE -ne 0) {
    throw "docker compose command failed."
}
