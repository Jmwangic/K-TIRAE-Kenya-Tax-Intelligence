# KRA Tax Anomaly Dashboard Overview

This dashboard helps reviewers understand tax anomalies, identify high-priority exceptions, and investigate mismatches across ETIMS, customs, and withholding data.

## 1. Purpose

The dashboard is designed to support operational review by highlighting unusual tax records and making them easy to interpret at a glance.

## 2. What the dashboard contains

- Summary cards: headline metrics showing the overall status of the reviewed dataset.
- Top risk items: the highest-priority anomalies ranked by severity and impact.
- Executive summary: a compact view for stakeholder or management review.
- Reconciliation findings table: detailed records showing mismatches between ETIMS and customs data.
- Duplicate invoice table: repeated invoice numbers and associated buyer taxpayer details.
- Timing gap table: invoice records that are unusually far apart in time.
- Detail panel: a drill-down view for a selected record when additional investigation is needed.
- Filters: all, anomalies only, or matched only.
- Print report: for presentation and meeting sharing.

## 3. How the dashboard works

The dashboard reads data from PostgreSQL tables and reconciliation views created in the database layer.

The backend is a FastAPI application that exposes endpoints such as:

- /summary
- /findings
- /duplicate-invoices
- /timing-gaps

These endpoints return structured data that the front-end dashboard renders as cards, tables, and detail views.

The risk score is calculated in the browser based on finding type and variance between ETIMS and customs values, so the most important anomalies rise to the top.

Users can filter by all records, anomalies only, or matched records to narrow the review to relevant cases.

When a user clicks a row, the detail panel opens to display more context for that specific issue.

## 4. Reconciliation logic

The database layer reconciles tax data using SQL views that compare ETIMS, customs, and withholding records.

- Matched records are classified as matched.
- Records with value differences are flagged as amount mismatches.
- Records missing supporting ETIMS or customs data are flagged as missing ETIMS purchase or missing customs support.

This keeps the review logic deterministic, auditable, and aligned to the underlying source data.

## 5. Why it matters

The dashboard allows a reviewer to understand the overall status of the tax anomaly review at a glance.

It reduces the effort needed to find exceptions and focus on the highest-risk records first.

It supports operational review and makes the investigation process clearer for internal stakeholders and management.

## 6. Overall summary

This dashboard combines database-driven anomaly detection with a simple, readable reporting interface. It helps users answer three questions quickly:

1. How much is affected?
2. Which issues are most urgent?
3. Which records need deeper investigation?

This is the purpose of the dashboard: to convert raw data into a quick, understandable review tool for tax anomaly management.
