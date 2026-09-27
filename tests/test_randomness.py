from simulator.randomness import RandomStreams


def _draw(streams: RandomStreams, *name: str, n: int = 5) -> list[float]:
    stream = streams.stream(*name)
    return [stream.random() for _ in range(n)]


def test_same_seed_gives_the_same_numbers():
    assert _draw(RandomStreams(42), "demand") == _draw(RandomStreams(42), "demand")


def test_a_different_seed_gives_different_numbers():
    assert _draw(RandomStreams(42), "demand") != _draw(RandomStreams(43), "demand")


def test_streams_are_independent():
    alone = RandomStreams(42)
    busy = RandomStreams(42)
    _draw(busy, "payments", n=1_000)  # heavy use of another stream...

    assert _draw(alone, "demand") == _draw(busy, "demand")  # ...does not change this one


def test_a_stream_continues_where_it_left_off():
    streams = RandomStreams(42)
    first, second = _draw(streams, "demand"), _draw(streams, "demand")

    assert first != second
    assert streams.stream("demand") is streams.stream("demand")


def test_streams_can_be_named_per_entity():
    streams = RandomStreams(42)

    assert _draw(streams, "customer", "cust_1") != _draw(streams, "customer", "cust_2")
