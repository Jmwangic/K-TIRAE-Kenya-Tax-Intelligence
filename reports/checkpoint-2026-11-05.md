# K-TIRAE Project Checkpoint

## Status date

2026-11-05

## Current position

The project remains a synthetic-data prototype. This checkpoint verifies the test-scenario and diagram changes published in commit `b5ec276` (`Add realistic test scenarios and diagrams`). It is not approval for production use, real taxpayer data, or automated tax decisions.

## Verification completed

- Local full test suite: **47 passed** on Python 3.13.14 using the configured PostgreSQL test database.
- GitHub Actions CI for `b5ec276`: completed successfully, including PostgreSQL migrations and the test job. [View CI run](https://github.com/Jmwangic/K-TIRAE-Kenya-Tax-Intelligence/actions/runs/41954271096).
- Live Render read-only smoke tests: `/health`, `/summary`, `/findings`, `/risk-results`, and `/taxpayers/search?q=Northstar` all returned HTTP 200. Health returned `{"status":"ok","database":{"ok":1}}`; summary returned 3 synthetic taxpayers and 4 findings.
- Confirmed the local `main` branch matched `origin/main` at `b5ec276` before recording this checkpoint.
- Docker image build remains unverified: Docker Desktop's engine is not available in the local environment.
- Pytest emitted one Starlette/AnyIO deprecation warning; no tests failed.

## Work completed at this checkpoint

- Added two database-backed scenarios for monthly sales aggregation and reconciliation cent tolerance.
- Added the recommended test-scenario catalog and its authenticity rationale in `docs/test-scenarios.md`.
- Added standalone Mermaid execution-flow and scenario-coverage diagrams in `docs/test-case-diagrams.md`.
- The scenario documentation distinguishes implementation tests from domain validation. Prototype thresholds and matching rules are assumptions, not official policy.

## Outstanding risks and next actions

1. **Database continuity:** the prior checkpoint says the replacement free Render database is scheduled to expire on 2026-11-24. Export and securely retain a backup, then plan and verify a restore drill before expiry.
2. **Administrator setup:** the prior checkpoint reported that no first administrator had been created. Confirm setup status and, if still needed, complete it through the dashboard using the private Render `ADMIN_SETUP_TOKEN`. Never record the token in source control or reports.
3. **Docker build:** retry the image build once Docker Desktop is running.
4. **Domain validation:** have a tax-domain reviewer confirm thresholds, duplicate-invoice scope, and reconciliation matching assumptions before representing them as operational rules.
5. **Deferred hardening:** add coverage for concurrent first-admin setup, rollback when audit persistence fails, broader input boundaries, browser accessibility/responsiveness, and database recovery.

## Safety boundary

All verification here used synthetic test data or read-only public endpoints. A passing test suite and healthy demo do not establish suitability for operational use. Keep human review and synthetic-data safeguards in place.
