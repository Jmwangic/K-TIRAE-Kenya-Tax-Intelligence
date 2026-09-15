# KRA Tax Anomaly Detection

First milestone: reconcile eTIMS invoices against customs imports and withholding records in PostgreSQL.

## Delivery plan

The five-week K-TIRAE delivery plan, acceptance criteria, risks, and two-hour checkpoint format are in [PROJECT_PLAN.md](PROJECT_PLAN.md). Weekly reports are stored in [reports/](reports/), using [WEEKLY_REPORT_TEMPLATE.md](WEEKLY_REPORT_TEMPLATE.md).

The repository includes a GitHub Actions workflow that creates or updates a progress-checkpoint issue every two hours. GitHub Actions schedules run in UTC and are reminders; the team still needs to record the actual evidence in the weekly report.

<!-- K-TIRAE-PROGRESS:START -->
## Live Progress

- Last automated checkpoint: 2026-09-15T15:12:34.991Z UTC
- Current delivery phase: Week 1 - requirements, architecture, and data contract
- Checkpoint workflow: [view run](https://github.com/Jmwangic/K-TIRAE-Kenya-Tax-Intelligence/actions/runs/34986859517)
- Detailed evidence: [weekly reports](reports/)

The GitHub Actions checkpoint workflow updates this section every two hours in UTC.
<!-- K-TIRAE-PROGRESS:END -->

## Scope

This starter slice includes:

- taxpayer, eTIMS invoice, customs import, and withholding tables;
- a reconciliation view using `FULL OUTER JOIN`;
- window-function checks for invoice timing gaps and repeated invoice numbers;
- seed data with one deliberate amount mismatch and one duplicate invoice number.

## Run locally

Requires PostgreSQL 15 or later. PostGIS is optional for this milestone and is enabled when available.

```sql
CREATE DATABASE kra_anomaly;
```

Run the files in order with `psql`:

```powershell
psql -U postgres -h localhost -d kra_anomaly -f db/001_schema.sql
psql -U postgres -h localhost -d kra_anomaly -f db/002_reconciliation.sql
psql -U postgres -h localhost -d kra_anomaly -f db/003_seed.sql
```

Then inspect the findings:

```sql
SELECT * FROM audit.reconciliation_findings;
SELECT * FROM audit.duplicate_invoice_numbers;
SELECT * FROM audit.invoice_timing_gaps;
```

## API layer

The project also includes a minimal FastAPI service exposing the anomaly results.

1. Create the local environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

2. Start the API:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_api.ps1
```

3. Query the service:

```powershell
Invoke-WebRequest http://127.0.0.1:8001/health
Invoke-WebRequest http://127.0.0.1:8001/findings
Invoke-WebRequest http://127.0.0.1:8001/duplicate-invoices
```

The seed data is synthetic and must not be used for operational decisions. Real deployment will require access controls, data-provenance checks, human review, and documented false-positive handling.
