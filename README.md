# Close-Ready

A month-end close data platform for a simulated financial advisory firm that sells prepaid advisory sessions through Stripe in multiple currencies.

It builds a **double-entry general ledger** from Stripe events, runs a **three-way reconciliation** (Stripe ↔ bank ↔ ledger), handles **revenue recognition** and **period close**, and enforces audit-ready controls as automated data tests.

> **Status:** work in progress — Phase 1 (business simulator and ingestion).

## Planned stack

Python · Stripe API · dlt · DuckDB · dbt · Snowflake · Evidence · GitHub Actions · Claude API

## Run the simulator

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv run python -m simulator backfill   # simulate the history before the cutover date
uv run pytest                         # run the tests
```

The backfill writes the simulated business events to `data/ground_truth/events.jsonl` and prints the first year's volumes next to the estimates in [docs/simulation.md](docs/simulation.md).

## Documentation

- [Accounting policy](docs/accounting_policy.md) — chart of accounts, posting rules, FX and close policy
- [Business simulation](docs/simulation.md) — how the Company's activity is simulated, and why
- [Architecture decision records](docs/decisions/)
