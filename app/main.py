import os
from typing import Any

import psycopg
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/kra_anomaly",
)

app = FastAPI(title="KRA Tax Anomaly API", version="0.1.0")


def get_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


@app.get("/", response_class=HTMLResponse)
def dashboard_page() -> str:
    return """
    <html>
      <head>
        <title>KRA Tax Anomaly Dashboard</title>
        <style>
          :root {
            --kra-blue: #0f4c81;
            --kra-blue-dark: #0a3557;
            --kra-gold: #f5b700;
            --kra-gold-soft: #fff1b8;
            --kra-green: #1e7a5d;
            --kra-green-soft: #dff7ef;
            --kra-red: #c13d3d;
            --kra-red-soft: #fde6e6;
            --kra-slate: #17324a;
            --kra-bg: #edf3f9;
            --kra-card: #ffffff;
            --kra-text: #18314f;
            --kra-muted: #58728a;
          }
          body { font-family: Arial, sans-serif; margin: 0; background: linear-gradient(180deg, var(--kra-bg) 0%, #f7fafc 100%); color: var(--kra-text); }
          .page-shell { max-width: 1500px; margin: 0 auto; padding: 28px 22px 40px; }
          .header-panel { background: linear-gradient(135deg, var(--kra-blue-dark) 0%, var(--kra-blue) 55%, var(--kra-gold) 160%); color: white; border-radius: 18px; padding: 28px 30px; margin-bottom: 22px; box-shadow: 0 16px 28px rgba(15, 76, 129, 0.22); }
          h1 { margin: 0; font-size: 40px; letter-spacing: -0.04em; }
          .subtitle { margin-top: 10px; color: #e9f4ff; font-size: 15px; }
          .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 16px; margin: 18px 0 24px; }
          .metric { background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%); border-radius: 16px; padding: 18px 18px 16px; box-shadow: 0 6px 18px rgba(15, 76, 129, 0.08); border-left: 6px solid #d9e5ef; }
          .metric:nth-child(1) { border-left-color: var(--kra-blue); }
          .metric:nth-child(2) { border-left-color: var(--kra-green); }
          .metric:nth-child(3) { border-left-color: var(--kra-gold); }
          .metric:nth-child(4) { border-left-color: var(--kra-red); }
          .metric-label { display: block; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--kra-muted); }
          .metric-value { display: block; font-size: 30px; font-weight: 800; margin-top: 10px; line-height: 1.1; }
          .metric-note { display: block; color: var(--kra-muted); font-size: 12px; margin-top: 4px; }
          .priority-panel { margin: 0 0 22px; background: white; border-radius: 18px; box-shadow: 0 8px 20px rgba(15, 76, 129, 0.08); border: 1px solid #dfeaf5; padding: 18px 20px; }
          .priority-header { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
          .priority-title { font-size: 18px; font-weight: 800; color: var(--kra-blue-dark); }
          .priority-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
          .priority-item { border: 1px solid #dfeaf5; border-radius: 12px; background: linear-gradient(180deg, #ffffff 0%, #f8fbfe 100%); padding: 14px 14px 12px; }
          .priority-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
          .priority-taxpayer { font-weight: 800; color: var(--kra-blue-dark); }
          .priority-risk { font-size: 12px; font-weight: 800; color: #0f172a; }
          .priority-type { margin-top: 8px; font-size: 13px; color: var(--kra-muted); }
          .toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 8px 0 18px; flex-wrap: wrap; }
          .legend { display: flex; gap: 10px; flex-wrap: wrap; }
          .legend-item { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: #475569; }
          .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
          .filter-buttons { display: flex; gap: 8px; flex-wrap: wrap; }
          .filter-btn { border: 1px solid #bfd4ea; background: white; border-radius: 999px; padding: 7px 14px; font-size: 12px; font-weight: 700; color: var(--kra-slate); cursor: pointer; box-shadow: 0 1px 2px rgba(15, 76, 129, 0.08); }
          .filter-btn.active { background: var(--kra-blue); color: white; border-color: var(--kra-blue); }
          .action-btn { border: 1px solid var(--kra-gold); background: linear-gradient(180deg, #fff8dd 0%, #fff0b3 100%); border-radius: 999px; padding: 8px 14px; font-size: 12px; font-weight: 800; color: var(--kra-blue-dark); cursor: pointer; box-shadow: 0 2px 8px rgba(245, 183, 0, 0.2); }
          .risk-pill { display: inline-flex; min-width: 86px; align-items: center; justify-content: center; border-radius: 999px; padding: 6px 10px; font-size: 12px; font-weight: 800; }
          .detail-panel { margin: 0 0 18px; background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%); border: 1px solid #dfe7f1; border-radius: 16px; padding: 18px; box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06); }
          .detail-panel.hidden { display: none; }
          .detail-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
          .detail-title { font-size: 18px; font-weight: 800; }
          .detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 12px; }
          .detail-item { background: white; border: 1px solid #edf2f7; border-radius: 12px; padding: 10px 12px; }
          .detail-label { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: 0.07em; color: #64748b; }
          .detail-value { display: block; margin-top: 6px; font-size: 18px; font-weight: 700; }
          .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px; }
          .card { background: white; border-radius: 18px; padding: 18px 18px 12px; box-shadow: 0 10px 24px rgba(15, 76, 129, 0.08); overflow: visible; }
          .card.full-width { grid-column: 1 / -1; }
          .card h2 { margin: 0 0 8px; font-size: 20px; color: var(--kra-blue-dark); }
          .executive-panel { display: none; background: linear-gradient(180deg, #fefdf7 0%, #fffaf0 100%); border: 1px solid #f2d57d; border-radius: 18px; padding: 20px; margin: 0 0 20px; box-shadow: 0 8px 20px rgba(245, 183, 0, 0.08); }
          .executive-mode .executive-panel { display: block; }
          .executive-mode .grid { display: none; }
          .exec-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
          .exec-item { background: #fff; border: 1px solid #f2d57d; border-radius: 12px; padding: 12px 14px; }
          .exec-item strong { display: block; color: var(--kra-blue-dark); margin-bottom: 6px; }
          table { width: 100%; border-collapse: separate; border-spacing: 0; margin-top: 8px; table-layout: auto; }
          th, td { border-bottom: 1px solid #e2e8f0; text-align: left; padding: 14px 10px; vertical-align: middle; white-space: normal; word-break: break-word; overflow-wrap: anywhere; font-size: 15px; line-height: 1.45; }
          th { font-size: 11px; text-transform: uppercase; letter-spacing: 0.07em; color: #64748b; background: #f8fafc; }
          tbody tr { min-height: 60px; }
          tbody tr:nth-child(even) { background: #f8fafc; }
          tbody tr:hover { background: #eff6ff; }
          .status { font-weight: 700; display: inline-flex; align-items: center; justify-content: center; padding: 6px 10px; border-radius: 999px; white-space: nowrap; min-width: 100px; }
          .matched { background: rgba(22, 163, 74, 0.12); color: #166534; }
          .warning { background: rgba(245, 158, 11, 0.12); color: #b45309; }
          .alert { background: rgba(220, 38, 38, 0.12); color: #b91c1c; }
          .finding-label { display: inline-block; line-height: 1.4; }
          .muted { color: #64748b; }
          .review-btn { border: 1px solid #bfd4ea; background: white; border-radius: 8px; padding: 7px 10px; font-size: 12px; font-weight: 700; color: var(--kra-blue-dark); cursor: pointer; }
          .review-btn:hover { background: #eff6ff; }
          .risk-table { min-width: 820px; table-layout: fixed; }
          .risk-table th { white-space: nowrap; }
          .risk-table th:nth-child(1) { width: 9%; }
          .risk-table th:nth-child(2) { width: 12%; }
          .risk-table th:nth-child(3) { width: 14%; }
          .risk-table th:nth-child(4) { width: 38%; }
          .risk-table th:nth-child(5) { width: 12%; }
          .risk-table th:nth-child(6) { width: 15%; }
          .risk-table td:nth-child(4) { min-width: 280px; }
          .risk-table .status, .risk-table .risk-pill, .risk-table .review-btn { white-space: nowrap; }
          @media (max-width: 1100px) {
            .grid { grid-template-columns: 1fr; }
            .card { overflow-x: auto; }
          }
        </style>
      </head>
      <body>
        <div class="page-shell">
          <div class="header-panel">
            <h1>KRA Tax Anomaly Dashboard</h1>
            <div class="subtitle">Operational review of reconciliation, risk results, duplicate invoices, and case decisions.</div>
          </div>

          <div id="summary" class="summary"></div>

          <div id="priority-panel" class="priority-panel">
            <div class="priority-header">
              <div class="priority-title">Top risk items</div>
              <div class="muted">Highest priority review list</div>
            </div>
            <div id="priority-list" class="priority-list"></div>
          </div>

          <div id="detail-panel" class="detail-panel hidden">
            <div class="detail-header">
              <div class="detail-title" id="detail-title">Selected issue</div>
              <div id="detail-severity" class="status matched">Low</div>
            </div>
            <div class="detail-grid" id="detail-grid"></div>
          </div>

          <div class="toolbar">
            <div class="legend">
              <span class="legend-item"><span class="dot" style="background:#1e7a5d"></span> Matched</span>
              <span class="legend-item"><span class="dot" style="background:#f5b700"></span> Warning</span>
              <span class="legend-item"><span class="dot" style="background:#c13d3d"></span> Critical</span>
            </div>
            <div class="filter-buttons">
              <button class="filter-btn" data-filter="all">All</button>
              <button class="filter-btn active" data-filter="anomaly">Anomalies only</button>
              <button class="filter-btn" data-filter="matched">Matched only</button>
              <button class="action-btn" id="executive-toggle">Executive view</button>
              <button class="action-btn" id="print-report">Print report</button>
            </div>
          </div>

          <div id="executive-panel" class="executive-panel">
            <div class="priority-header">
              <div class="priority-title">Executive summary</div>
              <div class="muted">Board-ready risk overview</div>
            </div>
            <div id="executive-summary-grid" class="exec-grid"></div>
          </div>

          <div class="grid">
            <div class="card full-width">
              <h2>Reconciliation findings</h2>
              <table data-table-key="findings">
                <thead>
                  <tr>
                    <th data-sort-key="taxpayer_id">Taxpayer</th>
                    <th data-sort-key="event_date">Date</th>
                    <th data-sort-key="finding_type">Finding</th>
                    <th data-sort-key="risk_score">Risk</th>
                    <th data-sort-key="etims_taxable_amount">ETIMS</th>
                    <th data-sort-key="customs_value">Customs</th>
                    <th data-sort-key="variance">Variance</th>
                  </tr>
                </thead>
                <tbody id="findings-body"></tbody>
              </table>
            </div>
            <div class="card full-width">
              <h2>Risk results and case review</h2>
              <table class="risk-table" data-table-key="risk">
                <thead>
                  <tr>
                    <th data-sort-key="taxpayer_id">Taxpayer</th>
                    <th data-sort-key="risk_score">Score</th>
                    <th data-sort-key="risk_level">Level</th>
                    <th>Reason</th>
                    <th data-sort-key="review_status">Review</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody id="risk-body"></tbody>
              </table>
            </div>
            <div class="card">
              <h2>Duplicate invoice numbers</h2>
              <table data-table-key="duplicates">
                <thead>
                  <tr>
                    <th data-sort-key="invoice_number">Invoice</th>
                    <th data-sort-key="occurrence_count">Occurrences</th>
                    <th data-sort-key="buyer_taxpayer_ids">Buyers</th>
                  </tr>
                </thead>
                <tbody id="duplicates-body"></tbody>
              </table>
            </div>
            <div class="card">
              <h2>Invoice timing gaps</h2>
              <table data-table-key="gaps">
                <thead>
                  <tr>
                    <th data-sort-key="buyer_taxpayer_id">Buyer</th>
                    <th data-sort-key="invoice_number">Invoice</th>
                    <th data-sort-key="invoice_date">Invoice date</th>
                    <th data-sort-key="previous_invoice_date">Prev date</th>
                    <th data-sort-key="days_since_previous_invoice">Days gap</th>
                  </tr>
                </thead>
                <tbody id="gaps-body"></tbody>
              </table>
            </div>
          </div>
        </div>

        <script>
          const sortState = {
            findings: { key: 'risk_score', direction: 'desc' },
            risk: { key: 'risk_score', direction: 'desc' },
            duplicates: { key: 'occurrence_count', direction: 'desc' },
            gaps: { key: 'days_since_previous_invoice', direction: 'desc' }
          };

          function computeRiskScore(row) {
            const base = row.finding_type === 'matched' ? 0 : row.finding_type === 'amount_mismatch' ? 68 : 86;
            const amountSpread = Math.abs(Number(row.etims_taxable_amount || 0) - Number(row.customs_value || 0));
            const varianceBoost = Math.min(18, amountSpread / 1000000);
            return Math.round(base + varianceBoost);
          }

          function getSeverity(type) {
            if (type === 'matched') return { label: 'Low', cls: 'matched' };
            if (type === 'amount_mismatch') return { label: 'Medium', cls: 'warning' };
            return { label: 'High', cls: 'alert' };
          }

          function formatMoney(value) {
            const num = Number(value || 0);
            return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
          }

          function renderPriorityList(rows) {
            const panel = document.getElementById('priority-list');
            const anomalies = rows.filter((row) => row.finding_type !== 'matched').slice().sort((a, b) => computeRiskScore(b) - computeRiskScore(a)).slice(0, 5);

            if (!anomalies.length) {
              panel.innerHTML = '<div class="priority-item"><div class="priority-type">No anomalies in the current filter.</div></div>';
              return;
            }

            panel.innerHTML = anomalies.map((row) => {
              const info = getSeverity(row.finding_type || 'matched');
              return `
                <div class="priority-item">
                  <div class="priority-row">
                    <div class="priority-taxpayer">${row.taxpayer_id}</div>
                    <span class="status ${info.cls} priority-risk">${computeRiskScore(row)}/100</span>
                  </div>
                  <div class="priority-type">${row.finding_type}</div>
                  <div class="muted" style="margin-top: 8px;">${row.event_date} · ${formatMoney(Math.abs(Number(row.etims_taxable_amount || 0) - Number(row.customs_value || 0)))}</div>
                </div>
              `;
            }).join('');
          }

          function renderExecutiveSummary(rows) {
            const container = document.getElementById('executive-summary-grid');
            const anomalies = rows.filter((row) => row.finding_type !== 'matched').slice().sort((a, b) => computeRiskScore(b) - computeRiskScore(a)).slice(0, 4);

            const summary = [
              ['Highest-risk taxpayer', anomalies[0]?.taxpayer_id || 'N/A'],
              ['Most urgent issue', anomalies[0]?.finding_type || 'No anomalies'],
              ['Anomaly count', rows.filter((row) => row.finding_type !== 'matched').length],
              ['Watchlist size', anomalies.length]
            ];

            container.innerHTML = summary.map(([label, value]) => `
              <div class="exec-item">
                <strong>${label}</strong>
                <div>${value}</div>
              </div>
            `).join('');
          }

          function showDetail(row) {
            const panel = document.getElementById('detail-panel');
            const grid = document.getElementById('detail-grid');
            const title = document.getElementById('detail-title');
            const severity = document.getElementById('detail-severity');
            const info = getSeverity(row.finding_type || 'matched');

            title.textContent = `${row.taxpayer_id || row.buyer_taxpayer_id || 'Record'} — ${row.finding_type || 'Record detail'}`;
            severity.textContent = info.label;
            severity.className = `status ${info.cls}`;

            const fields = [
              ['Taxpayer', row.taxpayer_id ?? row.buyer_taxpayer_id ?? '-'],
              ['Date', row.event_date ?? row.invoice_date ?? row.previous_invoice_date ?? '-'],
              ['Finding', row.finding_type ?? 'Record detail'],
              ['Risk score', `${computeRiskScore(row)}/100`],
              ['ETIMS', formatMoney(row.etims_taxable_amount ?? 0)],
              ['Customs', formatMoney(row.customs_value ?? 0)],
              ['Variance', formatMoney(Math.abs(Number(row.etims_taxable_amount || 0) - Number(row.customs_value || 0)))],
              ['Invoice', row.invoice_number ?? '-'],
              ['Occurrences', row.occurrence_count ?? '-'],
              ['Buyers', Array.isArray(row.buyer_taxpayer_ids) ? row.buyer_taxpayer_ids.join(', ') : (row.buyer_taxpayer_ids ?? '-')],
              ['Days gap', row.days_since_previous_invoice ?? '-']
            ];

            grid.innerHTML = fields
              .filter(([, value]) => value !== '-'
                || (Array.isArray(value) && value.length > 0))
              .map(([label, value]) => `
                <div class="detail-item">
                  <span class="detail-label">${label}</span>
                  <span class="detail-value">${value}</span>
                </div>
              `)
              .join('');

            panel.classList.remove('hidden');
          }

          async function loadSummary() {
            const res = await fetch('/summary');
            const summary = await res.json();
            const el = document.getElementById('summary');
            el.innerHTML = `
              <div class="metric">
                <span class="metric-label">Taxpayers analysed</span>
                <span class="metric-value">${summary.total_taxpayers}</span>
                <span class="metric-note">Synthetic review population</span>
              </div>
              <div class="metric">
                <span class="metric-label">Flagged taxpayers</span>
                <span class="metric-value">${summary.flagged_taxpayers}</span>
                <span class="metric-note">Require prioritisation</span>
              </div>
              <div class="metric">
                <span class="metric-label">Sales variance</span>
                <span class="metric-value">${formatMoney(summary.total_sales_variance)}</span>
                <span class="metric-note">Recorded versus declared</span>
              </div>
              <div class="metric">
                <span class="metric-label">Total findings</span>
                <span class="metric-value">${summary.total_findings}</span>
                <span class="metric-note">${summary.anomaly_findings} operational issues</span>
              </div>
              <div class="metric">
                <span class="metric-label">Matched</span>
                <span class="metric-value">${summary.matched_findings}</span>
                <span class="metric-note">Fully reconciled records</span>
              </div>
              <div class="metric">
                <span class="metric-label">Duplicates</span>
                <span class="metric-value">${summary.total_duplicates}</span>
                <span class="metric-note">Repeat invoice numbers</span>
              </div>
              <div class="metric">
                <span class="metric-label">Timing gaps</span>
                <span class="metric-value">${summary.total_timing_gaps}</span>
                <span class="metric-note">More than 30 days apart</span>
              </div>
            `;
          }

          function riskClass(level) {
            if (level === 'high') return 'alert';
            if (level === 'medium') return 'warning';
            return 'matched';
          }

          function renderRiskResults(rows, key = sortState.risk.key, direction = sortState.risk.direction) {
            const tbody = document.getElementById('risk-body');
            if (!tbody) return;

            const sorted = sortRows(rows, key, direction);
            tbody.innerHTML = sorted.length ? sorted.map((row) => `
              <tr>
                <td>${row.taxpayer_id}</td>
                <td><span class="risk-pill ${riskClass(row.risk_level)}">${row.risk_score}/100</span></td>
                <td class="status ${riskClass(row.risk_level)}">${row.risk_level}</td>
                <td>${row.reason}</td>
                <td>${row.review_status}</td>
                <td><button class="review-btn" data-taxpayer-id="${row.taxpayer_id}" data-status="${row.review_status}">${row.review_status === 'reviewed' ? 'Reopen' : 'Mark reviewed'}</button></td>
              </tr>
            `).join('') : '<tr><td colspan="6">No risk results</td></tr>';

            tbody.querySelectorAll('.review-btn').forEach((button) => {
              button.addEventListener('click', async () => {
                const taxpayerId = button.dataset.taxpayerId;
                const reviewed = button.dataset.status !== 'reviewed';
                const comments = window.prompt('Reviewer comments', '')
                  ?? '';
                const response = await fetch(`/case-reviews/${taxpayerId}`, {
                  method: 'PATCH',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    review_status: reviewed ? 'reviewed' : 'pending',
                    reviewer_comments: comments
                  })
                });
                if (!response.ok) {
                  window.alert('The case review could not be saved.');
                  return;
                }
                loadRiskResults();
              });
            });
          }

          async function loadRiskResults() {
            const response = await fetch('/risk-results');
            const rows = await response.json();
            renderRiskResults(rows);
            attachSortHandlers('risk', rows, renderRiskResults);
          }

          function sortRows(rows, key, direction) {
            const dir = direction === 'asc' ? 1 : -1;

            return [...rows].sort((a, b) => {
              let left = a[key];
              let right = b[key];

              if (key === 'event_date' || key === 'invoice_date' || key === 'previous_invoice_date') {
                left = Date.parse(left || '1970-01-01');
                right = Date.parse(right || '1970-01-01');
              } else if (key === 'risk_score' || key === 'taxpayer_id' || key === 'buyer_taxpayer_id' || key === 'occurrence_count' || key === 'days_since_previous_invoice' || key === 'etims_taxable_amount' || key === 'customs_value' || key === 'variance') {
                left = Number(left || 0);
                right = Number(right || 0);
              } else if (Array.isArray(left)) {
                left = left.join(', ');
                right = Array.isArray(right) ? right.join(', ') : right;
              }

              if (left < right) return -1 * dir;
              if (left > right) return 1 * dir;
              return 0;
            });
          }

          function attachSortHandlers(tableKey, rows, renderFunc) {
            const table = document.querySelector(`table[data-table-key="${tableKey}"]`);
            if (!table) return;

            table.querySelectorAll('th[data-sort-key]').forEach((header) => {
              header.style.cursor = 'pointer';
              header.addEventListener('click', () => {
                const key = header.dataset.sortKey;
                const current = sortState[tableKey];

                if (current.key === key) {
                  current.direction = current.direction === 'asc' ? 'desc' : 'asc';
                } else {
                  current.key = key;
                  current.direction = 'asc';
                }

                renderFunc(rows, current.key, current.direction);
              });
            });
          }

          function renderFindingsTable(rows, key = 'taxpayer_id', direction = 'asc', filter = 'anomaly') {
            const tbody = document.getElementById('findings-body');
            if (!tbody) return;

            const filtered = rows.filter((row) => {
              if (filter === 'all') return true;
              if (filter === 'anomaly') return row.finding_type !== 'matched';
              if (filter === 'matched') return row.finding_type === 'matched';
              return true;
            });

            const sorted = sortRows(filtered, key, direction);
            tbody.innerHTML = '';

            if (!sorted.length) {
              tbody.innerHTML = '<tr><td colspan="6">No records match this filter</td></tr>';
              return;
            }

            sorted.forEach((row) => {
              const tr = document.createElement('tr');
              tr._rowData = row;
              tr.innerHTML = formatFinding(row);
              tr.addEventListener('click', () => showDetail(row));
              tbody.appendChild(tr);
            });
          }

          function renderGenericTable(tableKey, endpoint, formatter, columns, rowsOverride) {
            const tbody = document.getElementById(`${tableKey}-body`);
            if (!tbody) return;

            const render = (rows, key = sortState[tableKey].key, direction = sortState[tableKey].direction) => {
              const sorted = sortRows(rows, key, direction);
              tbody.innerHTML = '';
              if (!sorted.length) {
                tbody.innerHTML = `<tr><td colspan="${columns}">No records</td></tr>`;
                return;
              }
              sorted.forEach((row) => {
                const tr = document.createElement('tr');
                tr._rowData = row;
                tr.innerHTML = formatter(row);
                tr.addEventListener('click', () => showDetail(row));
                tbody.appendChild(tr);
              });
            };

            if (rowsOverride) {
              render(rowsOverride);
              attachSortHandlers(tableKey, rowsOverride, render);
              return;
            }

            fetch(endpoint)
              .then((response) => response.json())
              .then((rows) => {
                render(rows);
                attachSortHandlers(tableKey, rows, render);
              })
              .catch(() => {
                tbody.innerHTML = `<tr><td colspan="${columns}">Unable to load data</td></tr>`;
              });
          }

          function formatFinding(row) {
            const type = row.finding_type;
            const labelMap = {
              matched: 'Matched',
              amount_mismatch: 'Amount mismatch',
              missing_etims_purchase: 'Missing ETIMS purchase',
              missing_customs_support: 'Missing customs support'
            };
            const cls = type === 'matched' ? 'matched' : type.includes('missing') ? 'alert' : 'warning';
            const etims = Number(row.etims_taxable_amount || 0);
            const customs = Number(row.customs_value || 0);
            const variance = Math.abs(etims - customs);
            const risk = computeRiskScore(row);
            return `
              <td>${row.taxpayer_id}</td>
              <td>${row.event_date}</td>
              <td class="status ${cls}"><span class="finding-label">${labelMap[type] || type}</span></td>
              <td><span class="risk-pill ${cls}">${risk}/100</span></td>
              <td>${formatMoney(etims)}</td>
              <td>${formatMoney(customs)}</td>
              <td>${formatMoney(variance)}</td>
            `;
          }

          function formatDuplicate(row) {
            return `
              <td>${row.invoice_number}</td>
              <td>${row.occurrence_count}</td>
              <td>${row.buyer_taxpayer_ids ? row.buyer_taxpayer_ids.join(', ') : '-'}</td>
            `;
          }

          function formatGap(row) {
            return `
              <td>${row.buyer_taxpayer_id}</td>
              <td>${row.invoice_number}</td>
              <td>${row.invoice_date}</td>
              <td>${row.previous_invoice_date}</td>
              <td>${row.days_since_previous_invoice}</td>
            `;
          }

          function bindFilterButtons() {
            const buttons = document.querySelectorAll('.filter-btn');
            buttons.forEach((button) => {
              button.addEventListener('click', () => {
                buttons.forEach((btn) => btn.classList.toggle('active', btn === button));
                const filter = button.dataset.filter;
                fetch('/findings')
                  .then((response) => response.json())
                  .then((rows) => {
                    const enriched = rows.map((row) => ({ ...row, risk_score: computeRiskScore(row) }));
                    renderPriorityList(enriched);
                    renderExecutiveSummary(enriched);
                    renderFindingsTable(enriched, sortState.findings.key, sortState.findings.direction, filter);
                  })
                  .catch(() => {
                    document.getElementById('findings-body').innerHTML = '<tr><td colspan="7">Unable to load findings</td></tr>';
                  });
              });
            });
          }

          loadSummary();
          bindFilterButtons();

          const pageShell = document.querySelector('.page-shell');
          document.getElementById('print-report').addEventListener('click', () => window.print());
          document.getElementById('executive-toggle').addEventListener('click', () => {
            const isExecutive = pageShell.classList.toggle('executive-mode');
            document.getElementById('executive-toggle').textContent = isExecutive ? 'Detailed view' : 'Executive view';
          });

          fetch('/findings')
            .then((response) => response.json())
            .then((rows) => {
              rows = rows.map((row) => ({ ...row, risk_score: computeRiskScore(row) }));
              renderPriorityList(rows);
              renderExecutiveSummary(rows);
              renderFindingsTable(rows, sortState.findings.key, sortState.findings.direction, 'anomaly');
              attachSortHandlers('findings', rows, (data, key, direction) => renderFindingsTable(data, key, direction, document.querySelector('.filter-btn.active')?.dataset.filter || 'anomaly'));
            });

          renderGenericTable('duplicates', '/duplicate-invoices', formatDuplicate, 3);
          renderGenericTable('gaps', '/timing-gaps', formatGap, 5);
          loadRiskResults();
        </script>
      </body>
    </html>
    """


@app.get("/summary")
def get_summary() -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total_findings FROM audit.reconciliation_findings")
            total_findings = cur.fetchone()["total_findings"]

            cur.execute("SELECT COUNT(*) AS anomaly_findings FROM audit.reconciliation_findings WHERE finding_type <> 'matched'")
            anomaly_findings = cur.fetchone()["anomaly_findings"]

            cur.execute("SELECT COUNT(*) AS matched_findings FROM audit.reconciliation_findings WHERE finding_type = 'matched'")
            matched_findings = cur.fetchone()["matched_findings"]

            cur.execute("SELECT COUNT(*) AS total_duplicates FROM audit.duplicate_invoice_numbers")
            total_duplicates = cur.fetchone()["total_duplicates"]

            cur.execute("SELECT COUNT(*) AS total_timing_gaps FROM audit.invoice_timing_gaps")
            total_timing_gaps = cur.fetchone()["total_timing_gaps"]

            cur.execute("SELECT COUNT(*) AS total_taxpayers FROM core.taxpayer")
            total_taxpayers = cur.fetchone()["total_taxpayers"]

            cur.execute("SELECT COUNT(*) AS flagged_taxpayers FROM audit.risk_results WHERE risk_score > 0")
            flagged_taxpayers = cur.fetchone()["flagged_taxpayers"]

            cur.execute("SELECT COALESCE(SUM(variance), 0) AS total_sales_variance FROM audit.sales_mismatches")
            total_sales_variance = cur.fetchone()["total_sales_variance"]

    return {
        "total_findings": total_findings,
        "anomaly_findings": anomaly_findings,
        "matched_findings": matched_findings,
        "total_duplicates": total_duplicates,
        "total_timing_gaps": total_timing_gaps,
        "total_taxpayers": total_taxpayers,
        "flagged_taxpayers": flagged_taxpayers,
        "total_sales_variance": total_sales_variance,
    }


@app.get("/health")
def health() -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            result = cur.fetchone()
    return {"status": "ok", "database": result}


@app.get("/findings")
def get_findings() -> list[dict[str, Any]]:
    query = "SELECT * FROM audit.reconciliation_findings ORDER BY taxpayer_id, event_date"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()


@app.get("/duplicate-invoices")
def get_duplicate_invoices() -> list[dict[str, Any]]:
    query = "SELECT * FROM audit.duplicate_invoice_numbers ORDER BY invoice_number"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()


@app.get("/timing-gaps")
def get_timing_gaps() -> list[dict[str, Any]]:
    query = "SELECT * FROM audit.invoice_timing_gaps ORDER BY buyer_taxpayer_id, invoice_date"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()



@app.get("/sales-mismatches")
def get_sales_mismatches() -> list[dict[str, Any]]:
    query = "SELECT * FROM audit.sales_mismatches ORDER BY taxpayer_id, tax_period"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()


@app.get("/risk-results")
def get_risk_results() -> list[dict[str, Any]]:
    query = "SELECT * FROM audit.risk_results ORDER BY risk_score DESC, taxpayer_id"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()


@app.patch("/case-reviews/{taxpayer_id}")
def update_case_review(taxpayer_id: int, payload: dict[str, str] = Body(...)) -> dict[str, Any]:
    status = payload.get("review_status", "pending")
    if status not in {"pending", "reviewed"}:
        raise HTTPException(status_code=400, detail="review_status must be pending or reviewed")

    comments = payload.get("reviewer_comments")
    query = """
        INSERT INTO audit.case_review (taxpayer_id, review_status, reviewer_comments)
        VALUES (%s, %s, %s)
        ON CONFLICT (taxpayer_id) DO UPDATE SET
            review_status = EXCLUDED.review_status,
            reviewer_comments = EXCLUDED.reviewer_comments,
            updated_at = now()
        RETURNING case_id, taxpayer_id, review_status, reviewer_comments, updated_at
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (taxpayer_id, status, comments))
            return cur.fetchone()
