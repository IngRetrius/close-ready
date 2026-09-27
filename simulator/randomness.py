"""Reproducible randomness, split into independent streams.

Each topic (demand, outcomes, payments...) or entity (one customer) gets its own random generator,
derived from the run seed and the stream's name. Drawing numbers in one stream never changes
another, so tuning one parameter does not reshuffle the rest of the simulated history.
"""

import hashlib
import random


class RandomStreams:
    def __init__(self, seed: int) -> None:
        self._seed = seed
        self._streams: dict[tuple[str, ...], random.Random] = {}

    def stream(self, *name: str) -> random.Random:
        """The generator for a stream, e.g. stream("demand") or stream("customer", customer_id)."""
        if name not in self._streams:
            self._streams[name] = random.Random(self._derive_seed(name))
        return self._streams[name]

    def _derive_seed(self, name: tuple[str, ...]) -> int:
        # hashlib instead of hash(): Python salts hash() for strings differently on every run
        key = "|".join((str(self._seed), *name)).encode()
        return int.from_bytes(hashlib.sha256(key).digest()[:8], "big")
