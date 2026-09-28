"""The backfill: the Company's simulated history before the cutover date (ADR-0001).

For now it writes the ground truth: the full log of business events, with when each one occurred and when
its source system recorded it. The platform never reads the ground truth; it is only used to evaluate the
platform's results (docs/simulation.md).
"""

from datetime import date
from pathlib import Path

from simulator.companies import CompaniesFlow
from simulator.config import SimulatorConfig
from simulator.engine import Engine
from simulator.events import write_jsonl
from simulator.individuals import IndividualsFlow


def simulate(config: SimulatorConfig, until: date) -> Engine:
    """Run the whole business, individuals and companies, from start_date to `until` (included)."""
    engine = Engine(config)
    engine.flows += [IndividualsFlow(engine), CompaniesFlow(engine)]
    engine.run(until)
    return engine


def write_ground_truth(engine: Engine, out_dir: Path) -> Path:
    """Write every event, in the order they occurred, to <out_dir>/ground_truth/events.jsonl."""
    path = out_dir / "ground_truth" / "events.jsonl"
    write_jsonl(engine.events, path)
    return path
