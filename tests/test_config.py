import copy
import tomllib
from datetime import date

import pytest
from pydantic import ValidationError

from simulator.config import CONFIG_PATH, SimulatorConfig, load_config


@pytest.fixture(scope="module")
def raw_config() -> dict:
    with CONFIG_PATH.open("rb") as file:
        return tomllib.load(file)


def test_repository_config_is_valid():
    config = load_config()

    assert config.run.timezone == "America/New_York"
    assert config.company.advisors == 3
    assert config.demand.seasonality.individuals.for_month(1) == 1.35


@pytest.mark.parametrize(
    ("product", "currency", "on", "expected_cents"),
    [
        ("individual_session", "usd", date(2025, 10, 1), 15_000),
        ("individual_session", "usd", date(2025, 12, 31), 15_000),
        ("individual_session", "usd", date(2026, 1, 1), 16_500),
        ("corporate_pack", "eur", date(2026, 3, 2), 80_000),
        ("corporate_pack", "gbp", date(2025, 11, 15), 64_000),
    ],
)
def test_price_uses_the_list_in_effect_on_the_date(product, currency, on, expected_cents):
    assert load_config().price(product, currency, on) == expected_cents


def test_price_before_the_first_list_is_an_error():
    with pytest.raises(LookupError):
        load_config().price("individual_session", "usd", date(2025, 9, 30))


def _set(path: str, value):
    """Return a function that sets a nested key of the raw config, e.g. 'run.timezone'."""

    def mutate(config: dict) -> None:
        *parents, key = path.split(".")
        node = config
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = value

    return mutate


INVALID_CONFIGS = [
    ("misspelled key", _set("individuals.markets.0.shre", 0.55), "Extra inputs are not permitted"),
    ("market shares", _set("individuals.markets.0.share", 0.50), "individuals.markets shares must add up to 1"),
    ("outcome shares", _set("individuals.outcomes.no_show", 0.10), "individuals.outcomes shares must add up to 1"),
    ("probability above 1", _set("disputes.win_rate", 1.2), "less than or equal to 1"),
    ("range out of order", _set("disputes.opened_after_days", {"min": 75, "max": 15}), "must not exceed max"),
    ("lead time mode", _set("individuals.lead_time_days.mode", 30), "min <= mode <= max"),
    ("seasonality average", _set("demand.seasonality.companies.dec", 2.0), "must average 1"),
    ("unknown timezone", _set("run.timezone", "Mars/Olympus"), "unknown timezone"),
    ("cutover before start", _set("run.cutover_date", date(2025, 9, 1)), "cutover_date must be after start_date"),
    ("no price on start date", _set("prices.0.effective_from", date(2025, 11, 1)), "no price for 'individual_session'"),
    ("discount above price", _set("loyalty_discount.usd", 20_000), "must be lower than the session price"),
    ("pays after write-off", _set("companies.payment_behavior.2.days_after_due", {"min": 31, "max": 95}), "pays after"),
    ("pack usage above pack size", _set("companies.usage_profiles.0.sessions_used", {"min": 10, "max": 12}), "between 1 and pack_sessions"),
]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [pytest.param(mutate, message, id=name) for name, mutate, message in INVALID_CONFIGS],
)
def test_invalid_config_is_rejected(raw_config, mutate, message):
    config = copy.deepcopy(raw_config)
    mutate(config)

    with pytest.raises(ValidationError, match=message):
        SimulatorConfig.model_validate(config)
