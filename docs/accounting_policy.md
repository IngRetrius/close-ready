# Accounting Policy

- **Status:** draft
- **Owner:** Juan Perea
- **Last updated:** 2026-09-26

This document defines how every business event becomes a journal entry. The data platform implements these rules; if the code and this document disagree, the code is wrong.

**Scope:** the order-to-cash cycle only (booking → billing → collection → cash in bank → revenue). Operating expenses such as payroll or rent are out of scope.

<!--
HOW TO WRITE THIS DOCUMENT
- Answer the guiding questions in each section, then delete them.
- Write for an accountant who has never seen the code.
- Every rule must be testable: someone should be able to check it with data.
- It is fine to draft in Spanish first and translate afterwards.
-->

## 1. The business

The Company is a financial advisory firm based in the United States. Its advisors deliver **4-hour advisory sessions**, remotely, to two customer segments worldwide:

- **Individuals (B2C):** personal finance guidance — budgeting, debt, saving and investment plans.
- **Companies (B2B):** financial advisory for small businesses and their teams.

**Functional currency:** USD. The books are kept in USD; Stripe settles in USD and the bank account is in USD.

**Customer currencies:** customers pay in EUR, USD or GBP. Each product has its own list price per currency; prices are not converted at checkout.

### Products

| Product | Segment | EUR | USD | GBP | Billing |
|---|---|---|---|---|---|
| Individual session (4 h) | Individuals | 150 | 165 | 130 | Paid in full by card at booking |
| Corporate pack (10 sessions) | Companies | 800 | 880 | 700 | Stripe invoice, payment due in 15 days |

**Loyalty discount:** an individual who books a new session within 4 months of their last attended session gets 50 off that session (EUR 50 / USD 55 / GBP 45). The invoice is issued at the discounted price.

### Delivery (when the customer receives what they paid for)

- A session is **delivered on the date it takes place**. The scheduling system, not Stripe, is the source of truth for delivery.
- Individual sessions take place 1–21 days after booking.
- **Cancellation policy (individuals):** cancelling 48 hours or more before the session gives a full refund. A later cancellation or a no-show gives no refund, and the session is **forfeited** on its scheduled date.
- **Corporate packs:** any employee of the customer can use the sessions. Packs are non-refundable and **expire 12 months after purchase**; sessions not used by then are forfeited.

### Data sources

| Facts | Source system |
|---|---|
| Invoices, charges, fees, refunds, disputes, payouts | Stripe |
| Bookings, attended sessions, cancellations, no-shows | Scheduling system (simulated) |
| Cash movements and bank fees | Bank statement (simulated) |
| Exchange rates | European Central Bank reference rates, via the Frankfurter API |

## 2. Chart of accounts

Codes follow the usual convention: 1xxx assets, 2xxx liabilities, 3xxx equity, 4xxx revenue, 6xxx operating expenses, 7xxx other income and expenses. Gaps between codes leave room for new accounts.

| Code | Account | Type | Normal balance | Holds |
|---|---|---|---|---|
| 1010 | Bank – operating account | Asset | Debit | Cash in the USD bank account. Must agree with the bank statement. |
| 1050 | Stripe clearing | Asset | Debit | Money collected by Stripe and not yet paid out to the bank. Must agree with the Stripe balance. |
| 1200 | Accounts receivable | Asset | Debit | Corporate pack invoices issued and not yet paid. |
| 2100 | Deferred revenue | Liability | Credit | Sessions paid or invoiced but not yet delivered or forfeited (contract liability). |
| 3000 | Owner's equity | Equity | Credit | Capital contributed by the owner, including the opening bank balance. |
| 3900 | Retained earnings | Equity | Credit | Profit of prior fiscal years, closed from the revenue and expense accounts at year-end. |
| 4000 | Advisory revenue – individuals | Revenue | Credit | Individual sessions delivered. |
| 4010 | Advisory revenue – companies | Revenue | Credit | Corporate pack sessions delivered. |
| 4050 | Forfeited sessions revenue | Revenue | Credit | Individual no-shows and late cancellations; corporate pack sessions unused at expiry (breakage). |
| 4100 | Refunds after delivery | Contra-revenue | Debit | Goodwill refunds of sessions already delivered. |
| 6100 | Payment processing fees | Expense | Debit | Stripe processing and currency conversion fees. |
| 6150 | Bank fees | Expense | Debit | Fees charged by the bank. |
| 6200 | Chargeback losses | Expense | Debit | Disputes lost, including dispute fees. |
| 6300 | Bad debt expense | Expense | Debit | Corporate invoices written off as uncollectible. |
| 7100 | Foreign exchange gain/loss – realized | Other income/expense | Debit or credit | Difference between the USD amount booked for a sale and the USD amount Stripe settled. |
| 7110 | Foreign exchange gain/loss – unrealized | Other income/expense | Debit or credit | Month-end revaluation of open receivables in EUR or GBP; reversed on the first day of the next month. |

### Design notes

- **Why a Stripe clearing account.** Stripe holds collected money for a few days, deducts its fees, and pays out one lump sum that covers many payments. Booking card payments straight to Bank would make the ledger disagree with the bank statement on every day in between, and would hide the fees inside the payout. The clearing account represents the money in transit; after each payout it should return to the balance Stripe reports.
- **Why accounts receivable exists only for companies.** Individuals pay by card at booking, so there is never an amount owed. Companies are invoiced with 15-day terms, so the Company holds a receivable until they pay.
- **Why refunds of individual sessions do not use 4100.** Refunds are only given 48 hours or more before the session, when the revenue has not been recognized yet. Those refunds reduce deferred revenue (2100). Account 4100 is only for exceptional refunds after delivery.
- **Why forfeited sessions have their own account.** Revenue from sessions nobody attended is recognized differently from delivered sessions and should be visible on its own in the income statement.
- **Why equity accounts exist in an order-to-cash ledger.** The bank account starts with an opening balance. Without an equity account on the other side of that entry, the trial balance could never sum to zero.

## 3. Posting rules

### General rules

1. Every journal entry balances: total debits equal total credits, in USD.
2. Every journal line keeps the source system and the source record ID, so any balance can be traced back to the event that created it.
3. **Two valuation sides.** Customer-side accounts (1200, 2100, 4xxx) are valued at the ECB rate of the invoice date. Cash-side accounts (1050, 1010) use the USD amounts that Stripe or the bank actually report. Any difference goes to 7100 (see section 4).
4. Events with no accounting effect produce no entry: a failed card payment, a loyalty discount (already reflected in the invoice price), a booking rescheduled to a new date.

### Individuals

| # | Event | Source | Debit | Credit | Amount | Entry date |
|---|---|---|---|---|---|---|
| 1 | Session booked and paid | Stripe | 1050 Stripe clearing | 2100 Deferred revenue | Invoice total | Payment date |
| 2 | Session attended | Scheduling | 2100 Deferred revenue | 4000 Revenue – individuals | Amount deferred for that booking | Session date |
| 3 | No-show or cancellation less than 48 h before | Scheduling | 2100 Deferred revenue | 4050 Forfeited sessions | Amount deferred for that booking | Scheduled session date |
| 4 | Cancellation 48 h or more before → refund | Stripe | 2100 Deferred revenue | 1050 Stripe clearing | Refund amount | Refund date |
| 5 | Goodwill refund after the session | Stripe | 4100 Refunds after delivery | 1050 Stripe clearing | Refund amount | Refund date |

### Companies

| # | Event | Source | Debit | Credit | Amount | Entry date |
|---|---|---|---|---|---|---|
| 6 | Pack invoice finalized | Stripe | 1200 Accounts receivable | 2100 Deferred revenue | Invoice total | Finalization date |
| 7 | Pack invoice paid | Stripe | 1050 Stripe clearing | 1200 Accounts receivable | Payment amount | Payment date |
| 8 | Pack session attended | Scheduling | 2100 Deferred revenue | 4010 Revenue – companies | Pack total ÷ 10 | Session date |
| 9 | Pack expires with unused sessions | Generated | 2100 Deferred revenue | 4050 Forfeited sessions | Unused sessions × (pack total ÷ 10) | Expiry date |
| 10 | Invoice marked uncollectible | Stripe | 2100 Deferred revenue (unused sessions) and 6300 Bad debt expense (sessions already delivered) | 1200 Accounts receivable | Open invoice amount | Date marked uncollectible |

Rule 10 splits the write-off: the Company cancels the pack, so the part of the receivable for sessions not yet delivered was never revenue and is simply reversed against deferred revenue. Only the part for sessions already delivered is a real loss.

### Stripe, bank and other events

| # | Event | Source | Debit | Credit | Amount | Entry date |
|---|---|---|---|---|---|---|
| 11 | Stripe fee on any transaction | Stripe | 6100 Payment processing fees | 1050 Stripe clearing | Fee on the balance transaction (a negative fee reverses the entry) | Balance transaction date |
| 12 | Dispute opened | Stripe | 6200 Chargeback losses | 1050 Stripe clearing | Disputed amount + dispute fee | Dispute date |
| 13 | Dispute won | Stripe | 1050 Stripe clearing | 6200 Chargeback losses | Amount Stripe returns | Date funds are returned |
| 14 | Payout to the bank | Stripe | 1010 Bank | 1050 Stripe clearing | Payout amount | Payout arrival date |
| 15 | Bank fee | Bank statement | 6150 Bank fees | 1010 Bank | Fee amount | Statement date |
| 16 | Opening balance | Manual | 1010 Bank | 3000 Owner's equity | Opening bank balance | First day of history |

Disputes are booked when Stripe withdraws the funds (rule 12), not when the dispute is decided, so that account 1050 always agrees with the Stripe balance. A won dispute reverses the loss (rule 13).

### Month-end

| # | Event | Source | Debit | Credit | Amount | Entry date |
|---|---|---|---|---|---|---|
| 17 | Revaluation of open receivables in EUR or GBP | Generated | Gain: 1200 Accounts receivable · Loss: 7110 Unrealized FX | Gain: 7110 Unrealized FX · Loss: 1200 Accounts receivable | Open amount at month-end rate − open amount at booked rate | Last day of the month |
| 18 | Reversal of rule 17 | Generated | Opposite of rule 17 | Opposite of rule 17 | Same as rule 17 | First day of the next month |

## 4. Foreign currency

### Rate source

European Central Bank euro reference rates, retrieved through the Frankfurter API. The ECB publishes one rate per currency against the euro on each TARGET business day, around 16:00 CET. On weekends and holidays, the most recent earlier rate applies (Frankfurter returns it automatically).

The ECB quotes every currency against the euro, so:

- **EUR → USD** uses the USD-per-EUR rate directly.
- **GBP → USD** uses the cross rate: USD per GBP = (USD per EUR) ÷ (GBP per EUR).
- **USD** needs no conversion.

### Which rate for which item

| Item | Rate |
|---|---|
| Invoice amount booked to 1200 and 2100 | ECB rate of the invoice date: the payment date for individuals, the finalization date for companies |
| Revenue released from 2100 (session delivered, forfeited or expired), refunds and write-offs of deferred amounts | The invoice's historical rate. Deferred revenue is never revalued. |
| Cash in 1050 and 1010 | The USD amount that Stripe or the bank actually reports |
| Open receivables at month-end | ECB rate of the last business day of the month |

### Realized differences (7100)

When a foreign-currency invoice is paid or refunded, the USD amount Stripe settles differs from the USD amount booked at the ECB rate. The difference is a realized gain or loss, recorded in 7100 within the same journal entry. Stripe's rate includes its own conversion margin, and this policy does not separate that margin from the market movement (see section 7).

### Unrealized differences (7110) and month-end revaluation

A receivable is a **monetary item**: the customer owes a fixed number of euros or pounds, so its USD value moves with the exchange rate. At each month-end, every open receivable in EUR or GBP is revalued at the month-end rate and the difference goes to 7110 (rule 17). The entry reverses on the first day of the next month (rule 18), so the payment entry always compares against the originally booked amount.

Deferred revenue is a **non-monetary item**: the Company owes a service, not an amount of currency. It stays at the historical rate.

### Rounding

Converted amounts are rounded to cents (half up) on each journal line. When an amount is split into parts — for example, a pack into 10 sessions — every part except the last is rounded, and the last part takes the remainder, so the parts always add up to the original amount.

### Worked example

A German company buys a corporate pack for EUR 800 on 2 March 2026 (ECB: 1.1698 USD per EUR). It pays late, on 8 April, and Stripe converts at 1.14 (illustrative).

| Date | Event | Debit | Credit |
|---|---|---|---|
| 2 Mar | Invoice finalized: 800 × 1.1698 | 1200 AR 935.84 | 2100 Deferred revenue 935.84 |
| 31 Mar | Revaluation: 800 × 1.1498 = 919.84 | 7110 Unrealized FX 16.00 | 1200 AR 16.00 |
| 1 Apr | Reversal of the revaluation | 1200 AR 16.00 | 7110 Unrealized FX 16.00 |
| 8 Apr | Payment: 800 × 1.14 = 912.00 | 1050 Stripe clearing 912.00 · 7100 Realized FX 23.84 | 1200 AR 935.84 |

Each session used from this pack releases 93.58 from deferred revenue (the tenth releases 93.62), at the 2 March rate, whatever the exchange rate is on the day of the session.

## 5. Revenue recognition

Revenue follows ASC 606 / IFRS 15. The five steps of the standard, applied to this business:

| Step | Individuals | Companies |
|---|---|---|
| 1. Identify the contract | Each paid booking | Each finalized pack invoice. The pack is non-cancellable and payment is due in 15 days, so the Company has an unconditional right to payment and records a receivable at invoicing (rule 6). |
| 2. Identify the performance obligations | One: the session | Ten: each session is a distinct service |
| 3. Determine the transaction price | The amount paid, net of any loyalty discount | The invoice total |
| 4. Allocate the price | All of it to the session | Equally to the 10 sessions (pack total ÷ 10, remainder on the tenth, see section 4) |
| 5. Recognize revenue | When the session takes place | As each session takes place |

A session lasts four hours on a single day, so each obligation is satisfied **at a point in time**: the session date. Revenue is never recognized at booking, invoicing or payment.

### Unused rights (forfeited sessions and breakage)

- **Individuals.** A no-show or a cancellation less than 48 hours before the session ends the customer's right to that session. The deferred amount is recognized in 4050 on the scheduled session date (rule 3).
- **Companies.** Sessions not used by the pack's expiry date are recognized in 4050 on that date (rule 9).

ASC 606 allows two methods for breakage: recognizing it gradually, in proportion to the sessions used, when the Company can reliably estimate how many sessions will go unused; or recognizing it when the chance of the customer using the remaining sessions becomes remote. The Company has no history to base an estimate on, so it uses the second method and recognizes breakage **at expiry**. This choice should be reviewed once there are at least 12 months of expired packs.

### Loyalty discount

The discount is recorded as a lower price on the discounted session, when that session is booked. Strictly, a discount on a future purchase that is only offered to returning customers can be a *material right*, a separate performance obligation that should receive part of the first session's price. This policy does not apply that treatment (see section 7).

### Refunds and write-offs

- A refund before the session reduces deferred revenue, not revenue (rule 4). A refund after the session goes to 4100 (rule 5).
- When a corporate invoice is written off, the sessions not yet delivered are cancelled and their deferred amount is reversed; only delivered sessions become bad debt (rule 10).

### Controls

These statements must hold at every month-end and are implemented as automated tests:

1. Every attended or forfeited session has exactly one revenue entry, dated on the session date.
2. No revenue is recognized before the session date.
3. For each invoice: revenue recognized + refunds and write-offs of deferred amounts + remaining deferred balance = invoice amount at the historical rate.
4. Deferred revenue per corporate pack = unused sessions × session amount.
5. Expired packs have a deferred balance of zero.
6. Deferred revenue roll-forward: opening balance + amounts invoiced − revenue recognized − refunds and write-offs = closing balance, and the closing balance agrees with account 2100.

### Worked example: revenue waterfall of one pack

A US company buys a pack for USD 880 on 15 January 2026 (USD 88 per session). It uses five sessions: two in February, one in April, one in July and one in November. The pack expires on 15 January 2027 with five sessions unused.

| Month | Sessions used | Revenue 4010 | Forfeited 4050 | Deferred balance at month-end |
|---|---|---|---|---|
| Jan 2026 | 0 | 0 | 0 | 880 |
| Feb 2026 | 2 | 176 | 0 | 704 |
| Apr 2026 | 1 | 88 | 0 | 616 |
| Jul 2026 | 1 | 88 | 0 | 528 |
| Nov 2026 | 1 | 88 | 0 | 440 |
| Jan 2027 | 0 | 0 | 440 | 0 |
| **Total** | **5** | **440** | **440** | |

Cash arrived in January 2026; revenue arrives over twelve months.

## 6. Period close

<!--
- When is a month considered closed?
- An event dated in a closed month arrives late (e.g., an August refund received in October). Where is it booked, and how is that traceable?
- Which controls must pass before a period can be closed?
-->

## 7. Simplifications and out of scope

<!--
List every simplification on purpose. Stating them shows judgment; hiding them looks like ignorance.
Examples: taxes, multi-entity consolidation, dispute accounting, month-end FX revaluation.
-->
