# Accounting Policy

- **Status:** draft
- **Owner:** Juan Perea
- **Last updated:** 2026-09-26

This document defines how every business event becomes a journal entry. The data platform implements these rules; if the code and this document disagree, the code is wrong.

**Scope:** the order-to-cash cycle only (booking → billing → collection → cash in bank → revenue). Operating expenses such as payroll or rent are out of scope.

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
| 3900 | Retained earnings | Equity | Credit | Cumulative result of prior fiscal years. Computed in reporting; no year-end closing entries are posted (see section 7). |
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

When a foreign-currency invoice is paid or refunded, the USD amount Stripe settles differs from the USD amount booked at the ECB rate. The difference is a realized gain or loss, recorded in 7100 within the same journal entry.

Stripe converts at a rate close to the market rate and reports its currency conversion fee separately, in the fee details of the balance transaction (for example, "Stripe currency conversion fee", 1% of the converted amount). That fee is booked to 6100 with the other Stripe fees (rule 11), so 7100 only reflects the difference between exchange rates. Any small spread left in Stripe's rate stays in 7100 (see section 7).

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

### Periods and close calendar

- Accounting periods are calendar months. The fiscal year is the calendar year.
- Each month closes on the **fifth business day of the following month** (BD5). Business days are Monday to Friday, excluding US federal holidays. The close calendar records, for every period, the date it was closed.
- A closed period is final: it is never reopened, and its reports can always be reproduced exactly as they were at close.

### Event date and posting period

Every journal entry carries two dates:

- **Event date:** when the event happened (the session date, the refund date, the bank statement date).
- **Posting period:** the period the entry belongs to in the books.

The posting period is the month of the event date **if that month is still open when the event is recorded**. If the month is already closed, the entry is posted to the first open period and flagged as a **late entry**, keeping its original event date and source record.

*Example:* an advisor records on 10 September that a customer did not show up on 29 August. August closed on 8 September (BD5; 7 September is Labor Day), so the forfeited-session revenue is posted to September, flagged as late, with event date 29 August.

To apply this rule, every source record must carry the timestamp when it became known to the Company (for example, when Stripe created the object or when the scheduling system was updated), not only the date of the event.

### Close checklist

A period can be closed only when all of these controls pass:

1. Every journal entry balances, and the trial balance sums to zero.
2. **Completeness:** every Stripe balance transaction and every session with a final status has its journal entry.
3. **Session statuses:** no session dated in the period is still pending (every past session is attended, cancelled or forfeited).
4. **Stripe:** the balance of 1050 agrees with the Stripe balance at period end.
5. **Bank reconciliation:** the balance of 1010 agrees with the bank statement, after listing every reconciling item with its cause and age.
6. **Deferred revenue:** the roll-forward (section 5, control 6) ties to account 2100.
7. **Expired packs** have been released to 4050 (rule 9).
8. **FX revaluation** of open receivables has been posted with the month-end rates (rule 17).
9. **Variance review:** every account whose balance changed materially against the previous month has a written explanation.

The checklist result is saved together with the snapshot of the trial balance at close.

## 7. Simplifications and out of scope

Each item below is a deliberate choice, not an oversight.

| Topic | What this policy does | What a full implementation would do |
|---|---|---|
| Taxes | Invoices carry no sales tax or VAT. | Calculate, collect and remit taxes per jurisdiction, with a tax liability account. |
| Scope | Order-to-cash only, one legal entity. | Include payables, payroll and fixed assets; consolidate entities and eliminate intercompany balances. |
| Year-end close | No closing entries; retained earnings are computed in reporting. | Post closing entries that move the year's result into 3900. |
| Loyalty discount | Treated as a lower price on the discounted session. | Evaluate it as a material right and allocate part of the earlier session's price to it. |
| Bad debts | Direct write-off when an invoice is marked uncollectible. | Estimate an allowance for expected credit losses (CECL / IFRS 9) every month. |
| Disputes | The disputed amount is expensed when Stripe withdraws it and reversed if won. The simulation only disputes sessions already delivered. | Hold disputed funds as a receivable until the outcome, and handle disputes on undelivered sessions against deferred revenue. |
| Stripe exchange rate spread | Stripe's explicit conversion fee goes to 6100; any spread built into Stripe's rate stays in realized FX (7100). | Compare Stripe's rate with the market rate at the moment of conversion and book the spread as a fee. |
| Breakage | Recognized at expiry. | Recognize proportionally once enough history exists to estimate it (see section 5). |
| Reopening periods | Not allowed; corrections are posted in the first open period. | A controlled reopen process with approval and audit trail. |
