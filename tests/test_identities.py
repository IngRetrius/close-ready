import random
import re

import pytest

from simulator.config import load_config
from simulator.identities import LOCALES, fake_person


def test_every_configured_country_has_a_name_locale():
    config = load_config()
    countries = {m.country for m in config.individuals.markets} | {m.country for m in config.companies.markets}

    assert countries <= LOCALES.keys()


def test_the_same_random_stream_gives_the_same_person():
    assert fake_person("FR", random.Random(7)) == fake_person("FR", random.Random(7))


@pytest.mark.parametrize("country", sorted(LOCALES))
def test_emails_are_plain_ascii_on_the_example_domain(country):
    _, email = fake_person(country, random.Random(3))

    assert re.fullmatch(r"[a-z0-9]+\.[a-z0-9]+\.\d+@example\.com", email)


def test_unknown_country_is_an_error():
    with pytest.raises(ValueError):
        fake_person("JP", random.Random(1))
