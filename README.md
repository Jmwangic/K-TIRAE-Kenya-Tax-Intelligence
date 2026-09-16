# KRA Tax Anomaly Detection

First milestone: reconcile eTIMS invoices against customs imports and withholding records in PostgreSQL.

## Delivery plan

The five-week K-TIRAE delivery plan, acceptance criteria, risks, and two-hour checkpoint format are in [PROJECT_PLAN.md](PROJECT_PLAN.md). Weekly reports are stored in [reports/](reports/), using [WEEKLY_REPORT_TEMPLATE.md](WEEKLY_REPORT_TEMPLATE.md).

The repository includes a GitHub Actions workflow that creates or updates a progress-checkpoint issue every two hours. GitHub Actions schedules run in UTC and are reminders; the team still needs to record the actual evidence in the weekly report.

The tracked project brief is [docs/K-TIRAE-project-brief.docx](docs/K-TIRAE-project-brief.docx). Its implementation notes and change procedure are in [docs/README.md](docs/README.md).

The brief-aligned database extension is applied by [db/004_brief_compliance.sql](db/004_brief_compliance.sql). It adds tax returns, sales-mismatch findings, explainable risk results, data-quality indicators, and a human case-review record. The API exposes `/taxpayers/search`, `/sales-mismatches`, `/risk-results`, and `PATCH /case-reviews/{taxpayer_id}` alongside the original reconciliation endpoints.

<!-- K-TIRAE-PROGRESS:START -->
## Live Progress

- Last automated checkpoint: 2026-09-16T14:30:44.967Z UTC
- Current delivery phase: Week 1 - requirements, architecture, and data contract
- Tracked brief SHA-256: `738c2627befc4439de2f8a4dbbb5ee5b4bcd2615915c50dc186570318f970ed3`
- Document review status: source tracked; requirement changes require human review
- Checkpoint workflow: [view run](https://github.com/Jmwangic/K-TIRAE-Kenya-Tax-Intelligence/actions/runs/35109015678)
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

## Share a live demo

The repository includes [render.yaml](render.yaml) and [Dockerfile](Dockerfile) for deploying a reviewable synthetic-data dashboard on Render.

1. Create or sign in to a Render account.
2. Choose **New > Blueprint** and connect `Jmwangic/K-TIRAE-Kenya-Tax-Intelligence`.
3. Deploy the blueprint. It creates a web service and a PostgreSQL database, applies the four SQL files at startup, and exposes the dashboard at a public Render URL.
4. Share the generated HTTPS URL with reviewers.

The public demo must use synthetic data only. Do not add real taxpayer records, production credentials, or unrestricted production integrations. The free Render database/service may sleep or expire, so use this as an academic review environment rather than an operational deployment.
