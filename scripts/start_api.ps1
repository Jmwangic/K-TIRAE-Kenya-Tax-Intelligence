param(
    [int]$Port = 8001,
    [string]$Host = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    throw "Python environment not found at $python. Run the project setup first."
}

$env:DATABASE_URL = 'postgresql://postgres:postgres@localhost:5432/kra_anomaly'
& $python -m uvicorn app.main:app --host $Host --port $Port
