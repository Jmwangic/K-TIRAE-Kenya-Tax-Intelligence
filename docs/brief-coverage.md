# Brief Coverage Matrix

| Brief requirement | Repository implementation | Status |
| --- | --- | --- |
| Taxpayer master data | `core.taxpayer` | Complete |
| eTIMS-style invoices | `source.etims_invoice` | Complete |
| Tax returns | `source.tax_return`, seeded by `db/004_brief_compliance.sql` | Complete |
| Sales mismatch | `audit.sales_mismatches`, threshold documented as a prototype assumption | Complete |
| Duplicate invoice detection | `audit.duplicate_invoice_numbers` and `audit.risk_results` | Complete |
| Explainable 0-100 risk score | `audit.risk_results` with points and reasons | Complete |
| Data-quality indicators | `audit.data_quality_findings` | Prototype coverage |
| Dashboard summary metrics | `/summary` includes taxpayers, flagged taxpayers, and sales variance | Complete |
| Taxpayer search | `/taxpayers/search` and dashboard search table show PIN, business, sales, variance, risk, and review status | Complete |
| Case review status/comments | `audit.case_review` and `PATCH /case-reviews/{taxpayer_id}` | Prototype coverage |
| Synthetic/anonymised data safeguards | Seed data and source governance documentation | Complete |
| Production KRA integration | Explicitly excluded | Not in scope |

The input VAT check remains a demonstration data-quality indicator and is not presented as official KRA policy.