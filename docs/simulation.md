# Business simulation

The Company does not exist, so its activity is simulated. This document explains how the simulator works and why its parameters have the values they have. The parameters themselves live in [`simulator/config.toml`](../simulator/config.toml), which is the single source of truth.

## Design

- **One engine, two outputs** ([ADR-0001](decisions/0001-stripe-data-source.md)). A single business engine decides what happens each day: who books, who attends, who pays late. Before the cutover date it writes records with the Stripe API schema (backfill); from the cutover date on it creates the same activity in the Stripe sandbox through the real API (live).
- **Reproducible.** The engine uses a fixed random seed: the same configuration always produces the same backfill.
- **Ground truth.** The engine knows the true story of every event (for example, that a bank deposit is late or that a customer was a no-show recorded days later). It writes that truth to a separate dataset used only to evaluate the platform, never as an input to it.
- **Time.** All timestamps are stored in UTC. Business dates — session days, month-ends, business days — follow the Company's timezone, `America/New_York`.
- **Money** is handled in minor units (cents), as in the Stripe API, to avoid floating-point rounding.

## The Company in numbers

### Capacity

| Parameter | Value | Why |
|---|---|---|
| Advisors | 3 | A small firm. With two 4-hour sessions per advisor per business day, capacity is about 1,500 sessions a year. |
| Sessions per advisor per day | 2 (09:00 and 14:00) | A 4-hour session fills a morning or an afternoon. |
| Working days | Monday–Friday, except US federal holidays | A US firm; weekend and holiday bookings are possible, sessions are not. |
| Maximum wait | 21 days | If no slot is free within 21 days, the customer goes elsewhere and the sale is lost. As demand grows, capacity becomes a real constraint, as it would for a growing firm. |

### Demand and growth

| Parameter | Value | Why |
|---|---|---|
| Start of operations | 1 October 2025 | Gives the backfill a clear beginning: a first-year firm. |
| Ramp-up | 30% → 100% of full demand over 6 months | A new firm builds its client base gradually. |
| Growth after ramp-up | 3% a month | Steady growth for a young firm; it keeps month-over-month comparisons interesting. |
| New individuals | 11 a week at full demand | Sized so advisors reach roughly 70–75% utilization by the end of the first year, the range professional-services firms usually aim for. |
| New companies | 2.5 a month at full demand | Corporate sales cycles are slower and fewer. |
| Seasonality, individuals | High in January (financial resolutions) and February–April (US tax season, 15 April deadline); low in summer and December | The typical calendar of personal finance demand in the US. |
| Seasonality, companies | High in January (new budgets) and October–November (budget planning and year-end spending); low in summer | The typical calendar of corporate training and advisory purchases. |

### Prices

| Parameter | Value | Why |
|---|---|---|
| Price list | Two lists: October–December 2025, and from 1 January 2026 (about +10%) | An annual price review. It separates a *price effect* from a *volume effect* when analysing revenue variances. |
| Loyalty discount | From 1 January 2026, launched with the new price list | Lets the analysis compare repeat behavior before and after the program. |
| Customer currencies | Individuals: 63% USD, 25% EUR, 12% GBP. Companies: 60% USD, 25% EUR, 15% GBP | A US firm with a strong European and British client base. |
| Card country | Customers in Canada, Mexico and Colombia pay in USD with non-US cards | Separates the two Stripe surcharges: the international card fee depends on where the card was issued, the conversion fee on the currency. |

### Individuals

| Parameter | Value | Why |
|---|---|---|
| Card declined at booking | 3%, of which 70% succeed on a retry | Produces failed charges, which must never create journal entries. |
| Booking lead time | 1–21 days, most often 5 | Short-notice professional appointments. |
| Outcomes | 85% attended, 8% cancelled with refund, 3% cancelled late, 4% no-show | Prepaid appointments have lower no-show rates than free ones, but never zero. |
| Rescheduled | 6% | No accounting effect, but moves revenue between months when a session crosses a month-end. |
| Return rate | 40% book again after an attended session; the wait follows a log-normal distribution (median 90 days, sigma 0.6, clipped to 20–300 days) | About two thirds of the returns fall inside the 4-month loyalty window. |
| Goodwill refunds | 1% of attended sessions | Rare, but they exercise account 4100. |

### Companies

| Parameter | Value | Why |
|---|---|---|
| Pack usage | 60% use all 10 sessions, 30% use 5–9, 10% use 1–4 | About 16% of pack sessions expire unused: material breakage that shows up in the income statement. |
| Usage span | 4–12 months | Some companies finish their pack quickly, others spread it out. |
| Payment | 70% on time, 22% up to 30 days late, 5% 31–60 days late, 3% never pay | Produces a realistic receivables aging, with a few write-offs a year. |
| Service hold | No new sessions after 30 days overdue | Standard credit control. It also limits the bad debt to sessions already delivered. |
| Write-off | 90 days overdue | The invoice is marked uncollectible (policy rule 10). |
| Repurchase | 55% buy a new pack 1–30 days after the current one is used up or expires; never after a write-off | Repeat corporate revenue. |
| Session booking | Requested 3–21 days in advance, most often 10 | Companies plan further ahead than individuals. |
| Cancellations | None: a scheduled pack session is either attended or a no-show | Simplification; individual customers already exercise cancellations and reschedules. |

### Payments and Stripe

| Parameter | Value | Why |
|---|---|---|
| Processing fee | 2.9% + USD 0.30; +1.5% for non-US cards | Observed in the sandbox (ADR-0001). |
| Currency conversion fee | 1% for charges not in USD | Observed in the sandbox (ADR-0001). |
| Stripe exchange rate | ECB rate with a small random difference (standard deviation 0.15%) | Stripe converts close to the market rate; the ECB rate is a daily reference, not the rate at the moment of the charge. |
| Disputes | 0.5% of attended individual sessions; opened 15–75 days after the charge, never before the session; decided 60–75 days later; 35% won | At the high end of what card-not-present businesses see, so that a year of data contains a few disputes. Only delivered sessions are disputed (accounting policy, section 7), and never one already refunded as a goodwill gesture. |
| Payouts | Daily, 2 business days after the charge | The sandbox account's schedule. |

### Data recording

| Parameter | Value | Why |
|---|---|---|
| Attendance and no-shows recorded | 90% the same day, 8% 1–5 days later, 2% 6–15 days later | Advisors sometimes update the scheduling system late. A record arrives after its month has closed only when a session near a month-end is recorded more than a week late: about once a year. That is enough to test the late-entry rule (policy, section 6). |
| Everything else | Recorded when it happens | Customers cancel online, and Stripe creates its objects in real time. |

## Expected volumes, first 12 months

Approximate figures from the parameters; the simulator reports the exact numbers.

| Metric | Approximate value |
|---|---|
| Individual customers | 470 |
| Individual bookings | 600 |
| Companies | 24 |
| Corporate packs | 31 |
| Card charges | 650 |
| Disputes | 2–3 |
| Advisor utilization | From about 15% in the first month to about 75% in the twelfth |

## Validation against live Stripe data

When live data exists (ADR-0001), the backfill is compared with it on:

1. Fee amounts by card country and currency.
2. The delay between a charge and the availability of its funds.
3. How charges are grouped into payouts, and the payout dates.
4. Whether refunds return the processing fee (assumed not).
5. Stripe's exchange rate against the ECB reference rate.

Each difference is either fixed in the simulator or documented here.

## Not simulated

- Taxes, as in the accounting policy.
- Payment methods other than cards (for example, ACH debits for US companies).
- Stripe's monthly billing fees, which are not deducted transaction by transaction.
- Costs of the Company other than payment and bank fees (the ledger covers the order-to-cash cycle only).
