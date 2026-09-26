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
| 7100 | Foreign exchange gain/loss | Other income/expense | Debit or credit | Realized difference between the rate used to book a sale and the rate Stripe settled at. |

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

## 4. Foreign currency

<!--
- Which rate is used to book an invoice issued in EUR or GBP? From which source, and for which date?
- Stripe converts the payment to USD at its own rate. Where does the difference go, and is it realized or unrealized?
- Do we revalue open receivables at month-end? (It is fine to say no, and explain why.)
-->

## 5. Revenue recognition

<!--
- When is revenue recognized: at invoice, at payment, or over the service period? Why? (ASC 606 / IFRS 15, one performance obligation)
- Daily proration or whole months?
- What happens to deferred revenue on a refund, a cancellation, a plan upgrade mid-period?
-->

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
