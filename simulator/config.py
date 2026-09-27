"""Load and validate the simulator parameters in config.toml.

Every business number the simulator uses comes from config.toml. This module turns that file
into typed, immutable objects and rejects it at startup if anything is inconsistent, so a typo
or a share that does not add up fails immediately instead of producing wrong data.
"""

import math
import tomllib
from collections.abc import Iterable
from datetime import date, time
from pathlib import Path
from typing import Annotated, Literal, get_args
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONFIG_PATH = Path(__file__).with_name("config.toml")

Currency = Literal["usd", "eur", "gbp"]
Product = Literal["individual_session", "corporate_pack"]
Probability = Annotated[float, Field(ge=0, le=1)]
Cents = Annotated[int, Field(gt=0)]
Factor = Annotated[float, Field(gt=0)]


def _check_shares(shares: Iterable[float], what: str) -> None:
    total = sum(shares)
    if not math.isclose(total, 1.0, abs_tol=1e-9):
        raise ValueError(f"{what} shares must add up to 1, got {total:.4f}")


class _Model(BaseModel):
    # extra="forbid" turns a misspelled key into an error; frozen=True makes the config read-only
    model_config = ConfigDict(extra="forbid", frozen=True)


class IntRange(_Model):
    min: int
    max: int

    @model_validator(mode="after")
    def _ordered(self) -> "IntRange":
        if self.min > self.max:
            raise ValueError(f"min ({self.min}) must not exceed max ({self.max})")
        return self


class TriangularDays(_Model):
    min: int = Field(ge=0)
    mode: int
    max: int

    @model_validator(mode="after")
    def _ordered(self) -> "TriangularDays":
        if not self.min <= self.mode <= self.max:
            raise ValueError(f"expected min <= mode <= max, got {self.min}, {self.mode}, {self.max}")
        return self


class LogNormalDays(_Model):
    """A skewed duration in days: most values near the median, a long tail to the right, clipped."""

    median: int = Field(gt=0)
    sigma: float = Field(gt=0)
    min: int = Field(ge=0)
    max: int

    @model_validator(mode="after")
    def _ordered(self) -> "LogNormalDays":
        if not self.min <= self.median <= self.max:
            raise ValueError(f"expected min <= median <= max, got {self.min}, {self.median}, {self.max}")
        return self


class MonthlyFactors(_Model):
    """Demand multiplier by calendar month; they must average 1 so they only redistribute demand."""

    jan: Factor
    feb: Factor
    mar: Factor
    apr: Factor
    may: Factor
    jun: Factor
    jul: Factor
    aug: Factor
    sep: Factor
    oct: Factor
    nov: Factor
    dec: Factor

    @model_validator(mode="after")
    def _average_is_one(self) -> "MonthlyFactors":
        average = sum(self.model_dump().values()) / 12
        if not math.isclose(average, 1.0, abs_tol=1e-6):
            raise ValueError(f"monthly factors must average 1, got {average:.4f}")
        return self

    def for_month(self, month: int) -> float:
        return list(self.model_dump().values())[month - 1]


class WeekdayWeights(_Model):
    """Demand weight by day of the week; they must average 1 so they only redistribute demand."""

    mon: Factor
    tue: Factor
    wed: Factor
    thu: Factor
    fri: Factor
    sat: Factor
    sun: Factor

    @model_validator(mode="after")
    def _average_is_one(self) -> "WeekdayWeights":
        average = sum(self.model_dump().values()) / 7
        if not math.isclose(average, 1.0, abs_tol=1e-6):
            raise ValueError(f"weekday weights must average 1, got {average:.4f}")
        return self

    def for_weekday(self, weekday: int) -> float:
        """Weight for date.weekday() (0 = Monday)."""
        return list(self.model_dump().values())[weekday]


class Market(_Model):
    country: str = Field(pattern=r"^[A-Z]{2}$")
    currency: Currency
    share: Probability


def _check_markets(markets: list[Market], what: str) -> None:
    _check_shares((m.share for m in markets), what)
    countries = [m.country for m in markets]
    if len(countries) != len(set(countries)):
        raise ValueError(f"{what} lists a country more than once")


class RunConfig(_Model):
    seed: int
    timezone: str
    start_date: date
    cutover_date: date

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError(f"unknown timezone {value!r}") from None
        return value

    @model_validator(mode="after")
    def _cutover_after_start(self) -> "RunConfig":
        if self.cutover_date <= self.start_date:
            raise ValueError("cutover_date must be after start_date")
        return self


class CompanyConfig(_Model):
    opening_bank_balance_usd: int = Field(ge=0)
    advisors: int = Field(ge=1)
    session_start_times: list[time] = Field(min_length=1)
    holiday_calendar: Literal["US"]
    max_wait_days: int = Field(ge=1)

    @field_validator("session_start_times")
    @classmethod
    def _unique_times(cls, value: list[time]) -> list[time]:
        if len(value) != len(set(value)):
            raise ValueError("session_start_times must not repeat")
        return value


class PriceEntry(_Model):
    product: Product
    effective_from: date
    usd: Cents
    eur: Cents
    gbp: Cents

    def amount(self, currency: Currency) -> int:
        return getattr(self, currency)


class LoyaltyDiscount(_Model):
    effective_from: date
    window_months: int = Field(ge=1)
    usd: Cents
    eur: Cents
    gbp: Cents


class Seasonality(_Model):
    individuals: MonthlyFactors
    companies: MonthlyFactors


class DemandConfig(_Model):
    ramp_up_months: int = Field(ge=0)
    ramp_start_level: float = Field(gt=0, le=1)
    monthly_growth_after_ramp: float = Field(ge=0)
    seasonality: Seasonality


class IndividualOutcomes(_Model):
    attended: Probability
    cancelled_with_refund: Probability
    cancelled_late: Probability
    no_show: Probability

    @model_validator(mode="after")
    def _shares(self) -> "IndividualOutcomes":
        _check_shares(self.model_dump().values(), "individuals.outcomes")
        return self


class IndividualsConfig(_Model):
    new_customers_per_week: float = Field(gt=0)
    booking_weekday_weights: WeekdayWeights
    checkout_decline_rate: Probability
    decline_retry_success_rate: Probability
    lead_time_days: TriangularDays
    reschedule_rate: Probability
    return_probability: Probability
    days_to_return: LogNormalDays
    goodwill_refund_rate: Probability
    outcomes: IndividualOutcomes
    markets: list[Market] = Field(min_length=1)

    @model_validator(mode="after")
    def _markets(self) -> "IndividualsConfig":
        _check_markets(self.markets, "individuals.markets")
        return self


class UsageProfile(_Model):
    name: str
    share: Probability
    sessions_used: IntRange


class PaymentBehavior(_Model):
    name: str
    share: Probability
    days_after_due: IntRange | None = None  # None: the company never pays

    @property
    def pays(self) -> bool:
        return self.days_after_due is not None


class CompaniesConfig(_Model):
    new_companies_per_month: float = Field(gt=0)
    pack_sessions: int = Field(ge=1)
    pack_validity_months: int = Field(ge=1)
    payment_terms_days: int = Field(ge=0)
    repurchase_probability: Probability
    repurchase_delay_days: IntRange
    lead_time_days: TriangularDays
    usage_span_months: IntRange
    no_show_rate: Probability
    service_hold_after_days_overdue: int = Field(ge=0)
    write_off_after_days_overdue: int = Field(ge=1)
    usage_profiles: list[UsageProfile] = Field(min_length=1)
    payment_behavior: list[PaymentBehavior] = Field(min_length=1)
    markets: list[Market] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> "CompaniesConfig":
        _check_markets(self.markets, "companies.markets")
        _check_shares((p.share for p in self.usage_profiles), "companies.usage_profiles")
        _check_shares((b.share for b in self.payment_behavior), "companies.payment_behavior")

        if not 1 <= self.usage_span_months.min <= self.usage_span_months.max <= self.pack_validity_months:
            raise ValueError("usage_span_months must lie between 1 and pack_validity_months")
        for profile in self.usage_profiles:
            if not 1 <= profile.sessions_used.min <= profile.sessions_used.max <= self.pack_sessions:
                raise ValueError(f"usage profile {profile.name!r} must use between 1 and pack_sessions sessions")
        if self.repurchase_delay_days.min < 0:
            raise ValueError("repurchase_delay_days must not be negative")
        if self.write_off_after_days_overdue <= self.service_hold_after_days_overdue:
            raise ValueError("write_off_after_days_overdue must be later than service_hold_after_days_overdue")
        for behavior in self.payment_behavior:
            if behavior.pays and behavior.days_after_due.max >= self.write_off_after_days_overdue:
                raise ValueError(
                    f"payment behavior {behavior.name!r} pays after the invoice would be written off"
                )
        return self


class DisputesConfig(_Model):
    rate: Probability
    opened_after_days: IntRange
    decided_after_days: IntRange
    win_rate: Probability


class StripeFees(_Model):
    card_percent: Probability
    card_fixed_usd: int = Field(ge=0)
    international_card_percent: Probability
    currency_conversion_percent: Probability
    dispute_fee_usd: int = Field(ge=0)
    refund_returns_fee: bool


class StripeFx(_Model):
    rate_noise_sd: float = Field(ge=0, lt=0.05)


class StripePayouts(_Model):
    interval: Literal["daily"]
    delay_business_days: int = Field(ge=0)


class StripeConfig(_Model):
    fees: StripeFees
    fx: StripeFx
    payouts: StripePayouts


class RecordingDelays(_Model):
    same_day: Probability
    days_1_to_5: Probability
    days_6_to_15: Probability

    @model_validator(mode="after")
    def _shares(self) -> "RecordingDelays":
        _check_shares(self.model_dump().values(), "recording_delays")
        return self


class SimulatorConfig(_Model):
    run: RunConfig
    company: CompanyConfig
    prices: list[PriceEntry] = Field(min_length=1)
    loyalty_discount: LoyaltyDiscount
    demand: DemandConfig
    individuals: IndividualsConfig
    companies: CompaniesConfig
    disputes: DisputesConfig
    stripe: StripeConfig
    recording_delays: RecordingDelays

    @model_validator(mode="after")
    def _prices_cover_the_simulation(self) -> "SimulatorConfig":
        keys = [(p.product, p.effective_from) for p in self.prices]
        if len(keys) != len(set(keys)):
            raise ValueError("a product has two price entries with the same effective_from")
        for product in get_args(Product):
            if not any(p.product == product and p.effective_from <= self.run.start_date for p in self.prices):
                raise ValueError(f"no price for {product!r} in effect on start_date {self.run.start_date}")
        return self

    @model_validator(mode="after")
    def _loyalty_discount_below_price(self) -> "SimulatorConfig":
        discount = self.loyalty_discount
        if discount.effective_from < self.run.start_date:
            raise ValueError("loyalty_discount.effective_from must not be before start_date")
        for currency in get_args(Currency):
            price = self.price("individual_session", currency, discount.effective_from)
            if getattr(discount, currency) >= price:
                raise ValueError(f"loyalty discount in {currency} must be lower than the session price")
        return self

    def price(self, product: Product, currency: Currency, on: date) -> int:
        """List price in cents for a product and currency, using the price list in effect on a date."""
        in_effect = [p for p in self.prices if p.product == product and p.effective_from <= on]
        if not in_effect:
            raise LookupError(f"no price for {product!r} in effect on {on}")
        return max(in_effect, key=lambda p: p.effective_from).amount(currency)


def load_config(path: Path = CONFIG_PATH) -> SimulatorConfig:
    """Read config.toml and validate it; raises pydantic.ValidationError describing every problem."""
    with path.open("rb") as file:
        return SimulatorConfig.model_validate(tomllib.load(file))
