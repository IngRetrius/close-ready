"""The backfill command: the whole business simulated, the ground truth written and the volumes reported."""

import json
from datetime import date, timedelta

import pytest

from simulator.__main__ import main
from simulator.backfill import simulate
from simulator.config import load_config
from simulator.report import first_year_checks


@pytest.fixture(scope="module")
def backfill():
    config = load_config()
    return simulate(config, config.run.cutover_date - timedelta(days=1))


def test_the_command_writes_the_ground_truth_and_a_report(tmp_path, capsys):
    assert main(["backfill", "--until", "2025-11-30", "--out", str(tmp_path)]) == 0

    lines = (tmp_path / "ground_truth" / "events.jsonl").read_text().splitlines()
    events = [json.loads(line) for line in lines]
    assert len(events) == len(simulate(load_config(), date(2025, 11, 30)).events)
    assert events[0]["event_type"] == "capital_contributed"
    assert [e["occurred_at"] for e in events] == sorted(e["occurred_at"] for e in events)

    output = capsys.readouterr().out
    assert "shorter than 12 months" in output
    assert f"Events: {len(events):,}" in output


@pytest.mark.parametrize("until", ["2025-09-30", "2026-10-19"])
def test_the_backfill_stays_between_the_start_and_the_cutover(until, tmp_path):
    # 2026-10-19 is the cutover date: from then on, activity goes to the live Stripe sandbox
    with pytest.raises(SystemExit):
        main(["backfill", "--until", until, "--out", str(tmp_path)])


def test_the_backfill_includes_both_segments(backfill):
    segments = {e.payload["segment"] for e in backfill.events if e.event_type == "customer_created"}

    assert segments == {"individual", "company"}


def test_first_year_volumes_match_the_documented_estimates(backfill):
    failed = [check for check in first_year_checks(backfill) if not check.ok]

    assert not failed, failed
