# Realistic Test Scenarios and Rationale

## Purpose and limits

This catalog defines repeatable scenarios for checking whether the prototype behaves plausibly against common reconciliation and review workflows. The records are synthetic, use Kenyan-style business identifiers and Kenya-shilling amounts, and are not copied from taxpayers or production systems.

These are prototype verification cases, not evidence that a rule is official KRA policy. In particular, the 20% sales variance threshold and 18% input-VAT ratio are demonstration assumptions. Confirm thresholds, identifiers, matching keys, and exception handling with authoritative requirements and a tax-domain reviewer before using them beyond a synthetic demonstration.

Authenticity comes from realistic data relationships and operational failure modes, not from using confidential records. Keep each case reproducible, include both positive and negative controls, calculate expected outcomes independently, record the rule/assumption behind each expected result, and preserve human review. Do not describe a flagged record as proof of non-compliance.

## Test flow

See the standalone [test case flow diagram](test-case-diagrams.md). It distinguishes what tests can establish (that the implementation follows its encoded assumptions) from what requires external evidence (that those assumptions match authoritative business rules).

## Recommended executable scenarios

| ID | Scenario and synthetic setup | Expected result | Why this case is recommended | Automation |
| --- | --- | --- | --- | --- |
| RT-01 | A business reports KSh 1,000.00 in monthly sales over two invoices of KSh 600.00 and KSh 610.00. | The month is aggregated to KSh 1,210.00; variance is KSh 210.00 (21%). One sales-mismatch result is returned. | Real ledgers contain multiple invoices per reporting period. This catches implementations that compare one invoice at a time instead of period totals. | `test_monthly_sales_aggregate_multiple_invoices_before_comparing_to_return` |
| RT-02 | Compare a KSh 100.00 eTIMS purchase with customs values of KSh 100.00, KSh 100.01, and KSh 100.02 for the same importer and date. | Exact and one-cent differences are `matched`; a two-cent difference is `amount_mismatch`. | Rounding and decimal precision create plausible near-matches. Testing both sides of the boundary makes the stated tolerance measurable rather than subjective. | `test_reconciliation_matches_exact_amount_and_applies_one_cent_tolerance` |
| RT-03 | Declared monthly sales are KSh 100.00; recorded sales are KSh 100.00 and exactly KSh 120.00. A separate case records KSh 121.00. | Exact matches and the 20% boundary are not flagged; the 21% case is flagged. | A negative control and a threshold boundary help reveal false positives and off-by-one/rounding errors. The threshold is a demonstration assumption only. | `test_sales_mismatch_normal_and_boundary_cases_are_not_flagged`; `test_sales_mismatch_flags_amounts_above_threshold` |
| RT-04 | An importer has an eTIMS purchase but no customs record; another importer has a customs record but no matching eTIMS purchase, on the same date. | The first is `missing_customs_support`; the second is `missing_etims_purchase`. | Real reconciliation is asymmetric: either source can be absent. Testing both directions verifies that unmatched rows are preserved rather than dropped by an inner join. | `test_reconciliation_includes_unmatched_etims_and_customs_records` |
| RT-05 | Input VAT equals 18% of declared purchases; a second synthetic return is one cent above that ratio. | At the boundary, no finding; above it, a data-quality finding. | This tests decimal boundary behavior and guards against rounding surprises. The 18% value is a prototype assumption, not a statement of tax law. | `test_input_vat_quality_rule_uses_strict_18_percent_boundary` |
| RT-06 | Two records use the same invoice number in different buyer/seller records; separately, attempt a repeated invoice number for the same seller. | The current prototype flags the cross-record repeated number; the database rejects a second number for the same seller. | Duplicate identity is a material real-world design choice. This test makes the current behavior visible, but issuer-scoped uniqueness versus global uniqueness must be validated with an eTIMS/domain reviewer before treating the flag as authentic. | `test_duplicate_invoice_and_risk_result_are_explainable`; `test_source_tables_reject_duplicate_and_invalid_records` |
| RT-07 | A reviewer without a valid administrator session attempts to change an invoice or case; an authorized reviewer edits a case. | Anonymous changes are rejected. Authorized changes preserve actor and before/after values in append-only audit history. | A useful review workflow must be both usable by authorized staff and resistant to unattributed edits. | `test_mutating_and_audit_routes_require_admin_session`; `test_case_review_update_records_before_and_after_values`; `test_admin_change_history_rejects_update_and_delete` |
| RT-08 | Apply all migrations/startup initialization more than once after adding a synthetic taxpayer and editing a return. | Existing taxpayer and edited return remain unchanged. | Deployment retries and restarts are routine operational events. This guards against data loss during redeployment. | `test_reapplying_all_migrations_preserves_existing_data` |

Run the automated database-backed cases after bootstrapping a disposable local PostgreSQL database:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_database_rules.py -vv -ra --tb=short
```

The test module uses `DATABASE_URL` when set and otherwise connects to the documented local `kra_anomaly` database. Never point destructive/replayable test setup at a production or live demo database. CI applies migrations to an isolated PostgreSQL service before running the full suite.

## Manual user-acceptance checks

Use only a disposable test database populated with synthetic records. Capture the input values, expected result, observed result, tester/date, and any discrepancy.

1. **Find and inspect a case:** search for a known synthetic taxpayer; verify the taxpayer, period, supporting records, score, reason, and review status shown by the dashboard agree with the database/API response.
2. **Review workflow:** sign in as a test administrator, mark a case reviewed with a short comment, reload it, and confirm the status/comment persist and the audit history identifies the actor and old/new values.
3. **No-indicator control:** use a synthetic taxpayer whose invoice total agrees with its return and whose records have no duplicate or quality indicator; verify the interface shows a low/no-indicator result rather than implying an allegation.
4. **Responsive/accessibility pass:** use keyboard-only navigation and a narrow mobile viewport; verify search, findings, and review controls remain usable and labels/statuses are understandable without relying only on color.

## Cases requiring domain decisions before they become pass/fail requirements

These are recommended real-world edge cases, but current behavior should not be called correct or incorrect until a domain reviewer confirms the expected rule:

- **Date/key alignment:** invoice, customs declaration, and withholding dates can differ even when records relate to the same economic event. Decide whether matching should use exact dates, a date window, period totals, or a stronger reference before setting a test oracle.
- **Duplicate-number scope:** confirm whether an invoice number is unique globally or within an issuer/series. The current schema prevents repeating a number for one seller, while the duplicate view detects a number shared across buyers. Validate the appropriate issuer, branch, credit-note, and series rules.
- **Zero declared sales with recorded invoices:** agree how to present the percentage variance when the denominator is zero. The current percentage calculation is undefined for zero, so do not infer a meaningful percentage without a defined display/risk rule.
- **Missing periods and amendments:** define how to handle absent returns, amended returns, credit notes, reversals, late submissions, and cancelled invoices; these are not represented fully in the current data model.
- **Withholding reconciliation:** agree which parties, periods, and amounts should be compared, and whether a withholding-only record is a missing eTIMS purchase or a separate review indicator.

## Evidence needed to claim greater authenticity

For each domain-dependent case, retain a short traceability record: requirement/source (including version/date), domain reviewer and approval date, synthetic input recipe, independently calculated expected result, automated/manual test evidence, and known limitations. Prefer published requirements and anonymised or purpose-generated examples. Do not use personal or taxpayer data without appropriate authority, legal basis, minimisation, and safeguards.
