# ADR-0001: Stripe data comes from a simulated backfill plus live sandbox activity

- **Status:** accepted
- **Date:** 2026-09-26

## Context

The platform needs about 12 months of Stripe history — invoices, charges, fees, refunds, disputes and payouts — to build the ledger, run the reconciliation and close past periods.

The plan was to generate that history in the Stripe sandbox with test clocks. A spike ([`spikes/stripe_test_clock.py`](../../spikes/stripe_test_clock.py)) created a clock frozen on 2 March 2026, invoiced a German customer EUR 150, paid the invoice and advanced the clock 60 days:

| Object | Carries the simulated date? | Observed |
|---|---|---|
| Invoice (created, finalized, paid) | Yes | 2 March 2026 |
| Charge | No | 27 September 2026 (real time) |
| Balance transaction | No | Created 27 September; available on 4 October |
| Balance and payouts | No | Advancing the clock changed neither |

Test clocks simulate the billing layer only. Money movement — charges, balance transactions and payouts — always runs in real time, so the sandbox cannot produce past cash activity.

The spike also showed how Stripe reports costs, which the simulator must reproduce:

- Processing fee: 2.9% + 1.5% for international cards + USD 0.30 (USD 7.82 on USD 170.86).
- Currency conversion: close to the market rate (0.1% from the ECB rate that day), with an explicit conversion fee of 1% (USD 1.71).
- Funds become available 7 days after the first charge; the payout schedule is daily with a 2-day delay.

## Decision

Stripe data comes from two sources that share the same schema:

1. **Historical backfill.** A simulator generates the 12 months before the cutover date. It writes records with the same structure as the Stripe API objects (Invoice, InvoicePayment, Charge, BalanceTransaction, Refund, Dispute, Payout), using real objects captured from the sandbox as templates, and applies the fee and payout rules observed above.
2. **Live activity.** From the cutover date on, a daily GitHub Actions workflow creates that day's business activity in the Stripe sandbox through the real API, and the pipeline ingests it incrementally.

Both modes share one business simulator — customers, bookings, attendance, cancellations — with two outputs: records written to files (backfill) or calls to the Stripe API (live). Every record carries its origin (`simulated_backfill` or `stripe_api`).

The **cutover date** is a single configuration value, set when the live workflow is ready (target: end of Phase 1, mid-October 2026).

**Lifecycle rule:** an object stays in the system where it was created for its whole life. A pack invoiced before the cutover is paid, refunded or disputed in the simulated data, even when that happens after the cutover. For a few weeks after the cutover both sources produce money movements, and the bank statement includes payouts from both — as it would if a company migrated between payment systems.

Test clocks are not used. The scheduling system and the bank statement are simulated in both periods; after the cutover, the bank statement is generated from the real Stripe payouts.

## Why

- **Live data only leaves the project poor.** By December there would be only two closed months, too little for reconciliation patterns, aging or trends.
- **Simulated data only makes the project look rigged.** A simulator only reproduces what its author believes Stripe does, and nothing would check it.
- **The hybrid gives both.** The backfill provides volume and history; the live data is real Stripe behavior and serves to validate the simulator. Backfill plus incremental loading is also the standard pattern when a company migrates systems.
- **It demonstrates automation.** The daily workflow runs unattended, like a production pipeline, and each month the platform closes a real period.

## Alternatives considered

- **A. Live data only:** rejected; too little history.
- **B. Simulator only:** rejected; no ingestion from a real API, and the simulator's assumptions would never be tested.
- **Test clocks for history:** rejected; charges, balance transactions and payouts ignore simulated time. They would produce invoices dated in the past paid by charges dated today.

## Consequences

**Easier**
- Realistic volume from day one, with known ground truth for the backfill.
- Real fees, timing and payouts for every month after the cutover.

**Harder**
- Two ingestion paths must produce identical schemas.
- The simulator must reproduce Stripe's fee and payout rules.
- The daily workflow must be idempotent and able to catch up after a missed day, or the live data will have gaps.
- GitHub disables scheduled workflows in public repositories after 60 days without activity.

**Validation**
Once live data exists, compare it with the backfill: fee amounts by card country and currency, the delay between charge and availability, and how charges are grouped into payouts. Every difference is either fixed in the simulator or documented.

**Revisit if**
- The sandbox does not create automatic payouts (to verify once funds become available, on 4 October 2026).
- Stripe test clocks start moving charges and balance transactions in simulated time.
