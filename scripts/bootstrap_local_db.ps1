param(
    [string]$User = 'postgres',
    [string]$Password = 'postgres',
    [string]$DbName = 'kra_anomaly'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$pgBin = 'C:\Program Files\PostgreSQL\17\bin'
$psql = Join-Path $pgBin 'psql.exe'
$createdb = Join-Path $pgBin 'createdb.exe'

if (-not (Test-Path $psql)) {
    throw "PostgreSQL client tools were not found at $pgBin. Please ensure PostgreSQL is installed."
}

$env:PGPASSWORD = $Password
$databaseList = & $psql -U $User -h localhost -d postgres -Atqc "SELECT datname FROM pg_database;"
if ($LASTEXITCODE -ne 0) {
    throw "Could not connect to PostgreSQL. Ensure the server is running and the postgres password is correct."
}

if ($databaseList -notmatch [regex]::Escape($DbName)) {
    & $createdb -U $User -h localhost -w $DbName
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create database $DbName"
    }
}

& $psql -U $User -h localhost -d $DbName -f (Join-Path $root 'db\001_schema.sql')
if ($LASTEXITCODE -ne 0) { throw 'Failed to apply 001_schema.sql' }

& $psql -U $User -h localhost -d $DbName -f (Join-Path $root 'db\002_reconciliation.sql')
if ($LASTEXITCODE -ne 0) { throw 'Failed to apply 002_reconciliation.sql' }

& $psql -U $User -h localhost -d $DbName -f (Join-Path $root 'db\003_seed.sql')
if ($LASTEXITCODE -ne 0) { throw 'Failed to apply 003_seed.sql' }

Write-Host "Database $DbName is ready."
Write-Host "Sample queries:"
Write-Host "  SELECT * FROM audit.reconciliation_findings;"
Write-Host "  SELECT * FROM audit.duplicate_invoice_numbers;"
Write-Host "  SELECT * FROM audit.invoice_timing_gaps;"
