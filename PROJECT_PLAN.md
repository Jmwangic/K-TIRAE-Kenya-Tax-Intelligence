# K-TIRAE Five-Week Delivery Plan

## Project boundary

K-TIRAE is an academic decision-support prototype. It uses synthetic or anonymised data to identify possible compliance indicators for human review. It does not connect to production KRA systems, use real taxpayer data, accuse taxpayers, or make automatic tax decisions.

## Delivery cadence

- Timeline: five weeks from the project start date agreed by the team.
- Progress checkpoint: every two hours while active development is underway.
- Weekly report: one report at the end of each week, committed to GitHub in `reports/`.
- Evidence standard: every completed item must have a code change, test result, screenshot, decision record, or documented reason for deferral.
- Review rule: no feature is considered complete without a reproducible test case and an explanation of the data source or assumption behind it.

## Five-week timeline

| Week | Focus | Required outcome | Exit evidence |
| --- | --- | --- | --- |
| 1 | Requirements, architecture, and data contract | Confirm scope, schema, synthetic-data rules, team responsibilities, and acceptance criteria | Approved requirements, data dictionary, architecture note, risk register |
| 2 | Synthetic data and database foundation | Generate controlled taxpayer, invoice, and return data; validate imports and relationships | Seed dataset, validation checks, schema migrations, import record counts |
| 3 | Compliance rules and explainable scoring | Implement sales mismatch, duplicate invoice, optional input VAT check if capacity allows, and 0–100 scoring | Rule queries, scoring logic, fixtures covering normal and flagged cases, API responses |
| 4 | Dashboard, case review, and security safeguards | Deliver taxpayer search, summary metrics, risk reasons, case status/comments, and basic access controls | Usable dashboard, review workflow, traceability mapping, manual test results |
| 5 | Integration, evaluation, and presentation | Stabilise the prototype, measure test results, document limitations, and prepare the final demonstration | Regression test run, user guide, ethics/data-protection note, presentation pack, final weekly report |

## Mandatory scope

1. Sales mismatch: compare recorded invoice sales with declared sales by taxpayer and tax period. The prototype threshold is a documented demonstration assumption, not an official KRA rule.
2. Duplicate invoice detection: identify repeated invoice numbers and preserve the supporting records.
3. Explainable risk scoring: combine triggered indicators into a score and risk level with reasons visible to a reviewer.

The high-input-VAT check is optional and must not delay the two mandatory checks or the final evaluation.

## Acceptance criteria

- All demonstration records are synthetic or anonymised and their generation is documented.
- Invalid records cover missing identifiers, duplicate records, invalid dates, missing invoice numbers, impossible values, and invalid VAT calculations.
- Each mandatory rule has normal, boundary, and flagged test cases.
- A reviewer can see the taxpayer, supporting transactions, triggered reasons, score, risk level, review status, and comments.
- Dashboard values can be traced to a database field, query, or explicit calculation.
- The documentation clearly states that a flag is not proof of wrongdoing and that human review is required.
- The final demonstration can be run from a clean setup using the repository instructions.

## Two-hour checkpoint format

At each active checkpoint, record:

- Current work and the commit or file changed.
- Evidence produced since the previous checkpoint.
- Test or validation result.
- Blocker, decision, or assumption.
- Next two-hour action.

## Dependencies and risks

| Risk | Mitigation |
| --- | --- |
| GitHub remote is not connected | Add the repository URL and push permissions before the first scheduled report is expected. |
| Scope expands beyond five weeks | Protect the mandatory checks; defer optional input VAT, advanced analytics, and production integrations. |
| Synthetic data is mistaken for official guidance | Label fixtures and thresholds as demonstration-only throughout the UI and documentation. |
| Risk score is interpreted as a tax decision | Show reasons, supporting records, review status, and the human-review disclaimer together. |
| Team work is difficult to evidence | Require small commits, weekly reports, and named ownership for each work package. |
