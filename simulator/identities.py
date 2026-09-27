"""Fictitious names and emails for simulated customers.

Names come from Faker in the customer's country locale. Emails always use example.com, a domain
reserved for examples, so no simulated email can reach a real person.
"""

import random
import unicodedata
from functools import cache

from faker import Faker

LOCALES = {
    "US": "en_US",
    "CA": "en_CA",
    "MX": "es_MX",
    "CO": "es_CO",
    "DE": "de_DE",
    "ES": "es_ES",
    "FR": "fr_FR",
    "NL": "nl_NL",
    "IT": "it_IT",
    "GB": "en_GB",
}


@cache
def _faker(locale: str) -> Faker:
    return Faker(locale)


def fake_person(country: str, rng: random.Random) -> tuple[str, str]:
    """A (name, email) pair, reproducible from the customer's random stream."""
    if country not in LOCALES:
        raise ValueError(f"no name locale configured for country {country!r}")
    fake = _faker(LOCALES[country])
    fake.seed_instance(rng.getrandbits(32))
    first, last = fake.first_name(), fake.last_name()
    email = f"{_ascii(first)}.{_ascii(last)}.{rng.randint(10, 9999)}@example.com"
    return f"{first} {last}", email


def _ascii(text: str) -> str:
    """'Grégoire' -> 'gregoire': accents removed, only letters and digits kept."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(char for char in plain.lower() if char.isalnum())
