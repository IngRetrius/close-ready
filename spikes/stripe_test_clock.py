"""Spike: do objects created under a Stripe test clock carry the simulated date?

Questions (the answers go into docs/decisions/0001-stripe-data-source.md):
1. Do invoices and charges created under a test clock carry the simulated date?
2. Do balance transactions (Stripe's internal ledger) carry the simulated date?
3. Do payouts happen in simulated time?

Run with: uv run python spikes/stripe_test_clock.py
"""

import os
import time
from datetime import datetime, timedelta, timezone

import requests
import stripe
from dotenv import load_dotenv

load_dotenv()
client = stripe.StripeClient(os.environ["STRIPE_SECRET_KEY"]).v1

START = datetime(2026, 3, 2, 10, 0, tzinfo=timezone.utc)
ADVANCE_TO = START + timedelta(days=60)
PRICE_EUR_CENTS = 15000  # Stripe amounts are integers in the smallest currency unit


def ts(unix: int | None) -> str:
    """Format a Stripe Unix timestamp as a readable UTC date."""
    if unix is None:
        return "-"
    return datetime.fromtimestamp(unix, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def ecb_usd_per_eur(day: datetime) -> float:
    """ECB reference rate for the given day (Frankfurter falls back to the last business day)."""
    url = f"https://api.frankfurter.app/{day:%Y-%m-%d}?from=EUR&to=USD"
    return requests.get(url, timeout=10).json()["rates"]["USD"]


def wait_until_ready(clock_id: str) -> None:
    """Advancing a clock is asynchronous: Stripe replays everything that happens in between."""
    while client.test_helpers.test_clocks.retrieve(clock_id).status != "ready":
        time.sleep(2)


# 1. A clock frozen in the past. Every object attached to it lives in simulated time.
clock = client.test_helpers.test_clocks.create(
    params={"frozen_time": int(START.timestamp()), "name": "spike-eur-session"}
)
print(f"Test clock {clock.id} frozen at {ts(clock.frozen_time)}\n")

# 2. A German individual with a German test card, attached to the clock.
customer = client.customers.create(
    params={
        "name": "Spike - German individual",
        "email": "spike.de@example.com",
        "test_clock": clock.id,
        "payment_method": "pm_card_de",
        "invoice_settings": {"default_payment_method": "pm_card_de"},
    }
)

# 3. One session invoiced in EUR: create the invoice, add the line, finalize it and pay it.
invoice = client.invoices.create(
    params={
        "customer": customer.id,
        "currency": "eur",
        "collection_method": "charge_automatically",
        "auto_advance": False,
    }
)
client.invoice_items.create(
    params={
        "customer": customer.id,
        "invoice": invoice.id,
        "amount": PRICE_EUR_CENTS,
        "currency": "eur",
        "description": "Individual advisory session (4 h)",
    }
)
client.invoices.finalize_invoice(invoice.id)
invoice = client.invoices.pay(invoice.id)

# 4. Follow the chain: Invoice -> InvoicePayment -> PaymentIntent -> Charge -> BalanceTransaction.
invoice_payment = client.invoice_payments.list(params={"invoice": invoice.id}).data[0]
intent = client.payment_intents.retrieve(
    invoice_payment.payment.payment_intent,
    params={"expand": ["latest_charge.balance_transaction"]},
)
charge = intent.latest_charge
bt = charge.balance_transaction

print("BEFORE ADVANCING THE CLOCK")
print(f"  Invoice {invoice.id}")
print(f"    created      {ts(invoice.created)}")
print(f"    finalized    {ts(invoice.status_transitions.finalized_at)}")
print(f"    paid         {ts(invoice.status_transitions.paid_at)}")
print(f"  Charge {charge.id}")
print(f"    created      {ts(charge.created)}   {charge.amount / 100:.2f} {charge.currency.upper()}")
print(f"  Balance transaction {bt.id}")
print(f"    created      {ts(bt.created)}")
print(f"    available_on {ts(bt.available_on)}   status: {bt.status}")
print(f"    amount       {bt.amount / 100:.2f} {bt.currency.upper()}   exchange_rate: {bt.exchange_rate}")
print(f"    fee          {bt.fee / 100:.2f}   net: {bt.net / 100:.2f}")
for fee in bt.fee_details:
    print(f"      - {fee.type}: {fee.amount / 100:.2f} ({fee.description})")

ecb = ecb_usd_per_eur(START)
booked_usd = round(PRICE_EUR_CENTS / 100 * ecb, 2)
print(f"\n  ECB rate on {START:%Y-%m-%d}: {ecb} -> booked at {booked_usd:.2f} USD")
print(f"  Stripe settled {bt.amount / 100:.2f} USD -> realized FX {bt.amount / 100 - booked_usd:+.2f} USD")

# 5. Move simulated time forward and look at the balance and payouts again.
print(f"\nAdvancing the clock to {ADVANCE_TO:%Y-%m-%d}...")
client.test_helpers.test_clocks.advance(
    clock.id, params={"frozen_time": int(ADVANCE_TO.timestamp())}
)
wait_until_ready(clock.id)

bt = client.balance_transactions.retrieve(bt.id)
print("\nAFTER ADVANCING THE CLOCK")
print(f"  Balance transaction status: {bt.status}   available_on {ts(bt.available_on)}")

balance = client.balance.retrieve()
print(f"  Balance available: {[(b.amount / 100, b.currency) for b in balance.available]}")
print(f"  Balance pending:   {[(b.amount / 100, b.currency) for b in balance.pending]}")

payouts = client.payouts.list(params={"limit": 5}).data
print(f"  Payouts found: {len(payouts)}")
for payout in payouts:
    print(
        f"    {payout.id}  created {ts(payout.created)}  arrival {ts(payout.arrival_date)}"
        f"  {payout.amount / 100:.2f} {payout.currency.upper()}  {payout.status}"
    )

print(f"\nNow (real time): {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
print(f"Clock kept for inspection: {clock.id} (deleting it also deletes its customer and invoices)")
