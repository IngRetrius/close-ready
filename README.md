# Close-Ready

A month-end close data platform for a simulated financial advisory firm that sells prepaid advisory sessions through Stripe in multiple currencies.

It builds a **double-entry general ledger** from Stripe events, runs a **three-way reconciliation** (Stripe ↔ bank ↔ ledger), handles **revenue recognition** and **period close**, and enforces audit-ready controls as automated data tests.

> **Status:** work in progress — Phase 1 (business simulator and ingestion).

## Planned stack

Python · Stripe API · dlt · DuckDB · dbt · Snowflake · Evidence · GitHub Actions · Claude API

## Documentation

- [Accounting policy](docs/accounting_policy.md) — chart of accounts, posting rules, FX and close policy
- [Architecture decision records](docs/decisions/)
