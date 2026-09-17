# K-TIRAE Weekly Progress Report

## Reporting period

- Week: 1
- Dates: 2026-09-15 to 2026-09-17
- Report owner: Project repository
- Repository commit: pending commit for test coverage and evidence updates

## Executive summary

The initial project brief was cross-checked against the repository. The existing customs and withholding reconciliation milestone was preserved, and the missing brief-aligned tax-return, sales-mismatch, explainable-risk, data-quality, and case-review foundations were added. The tracked DOCX remains the source of academic scope and all sample data remains synthetic.

## Completed work

| Work item | Owner | Evidence | Status |
| --- | --- | --- | --- |
| Add tax-return and case-review tables | Repository | `db/004_brief_compliance.sql` | Complete |
| Implement sales mismatch view using the documented 20% demonstration threshold | Repository | `audit.sales_mismatches` | Complete |
| Implement explainable risk results and reasons | Repository | `audit.risk_results` | Complete |
| Extend API summary and expose compliance/review endpoints | Repository | `/summary`, `/sales-mismatches`, `/risk-results`, `PATCH /case-reviews/{taxpayer_id}` | Complete |
| Document brief-to-code coverage | Repository | `docs/brief-coverage.md` | Complete |
| Track progress on GitHub every two hours | Repository | `.github/workflows/progress-report-reminder.yml` | Complete |
| Add repeatable database rule tests | Repository | `tests/test_database_rules.py`; 3 tests passed | Complete |

## Validation

- Python compilation: passed with `python -m py_compile app/main.py`.
- Workspace diagnostics: no errors in edited files.
- Migration/bootstrap wiring checks: passed.
- PostgreSQL execution: passed against local PostgreSQL 17 after fixing bootstrap idempotency. Docker Desktop was not required.
- API smoke tests: passed for `/health`, `/summary`, `/findings`, `/duplicate-invoices`, `/timing-gaps`, `/sales-mismatches`, and `/risk-results`.
- Taxpayer search smoke test: passed for `/taxpayers/search?q=Acme`.
- Case-review persistence: passed for `PATCH /case-reviews/2`; status returned as `reviewed`.
- Rule integration tests: passed, covering normal, exact-threshold, flagged mismatch, duplicate invoice, and explainable risk cases.

## Two-hour checkpoints

| Checkpoint | Progress since last checkpoint | Evidence | Blocker/decision | Next action |
| --- | --- | --- | --- | --- |
| 1 | Brief cross-check completed and gaps identified | Current repository and tracked DOCX | Preserve customs milestone while adding brief-aligned model | Apply migration and API changes |
| 2 | Migration, API endpoints, documentation, and coverage matrix added | Local validation results | PostgreSQL runtime unavailable | Run bootstrap and endpoint smoke tests when database is available |
| 3 | Added repeatable rule tests and reran the local validation path | `3 passed`; database bootstrap and API smoke tests passed | Docker verification remains pending | Verify the container build and deployment entrypoint |

## Scope and risk review

- Mandatory scope protected: sales mismatch, duplicate invoice detection, explainable scoring, synthetic data, and human review safeguards.
- New risk: container-based verification remains pending even though local PostgreSQL verification passed.
- Deferred work: full staged CSV data-quality importer, authentication, and optional high-input-VAT rule.

## Next week

1. Verify the Docker/Render deployment path.
2. Add controlled CSV import and validation fixtures for the remaining data-quality checks.
3. Add authentication and access-control safeguards before any non-synthetic deployment.
