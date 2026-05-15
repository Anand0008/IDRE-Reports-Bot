import time
from testing.v10_harness.measurements import Measurement, measure


def test_measurement_records_latency():
    # Use 50ms sleep to stay safely above Windows time.monotonic() ~16ms granularity
    with measure() as m:
        time.sleep(0.05)
    assert m.latency_ms >= 30  # generous lower bound for clock resolution
    assert m.latency_ms < 500  # not absurdly slow


def test_measurement_records_tokens():
    with measure() as m:
        m.record_tokens(prompt=100, completion=50)
    assert m.tokens.prompt == 100
    assert m.tokens.completion == 50
    assert m.tokens.total == 150


def test_measurement_serializes_to_dict():
    with measure() as m:
        m.record_tokens(prompt=10, completion=5)
    d = m.to_dict()
    assert "latency_ms" in d
    assert d["tokens"]["total"] == 15
