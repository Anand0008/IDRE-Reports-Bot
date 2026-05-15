import time
from testing.v10_harness.measurements import Measurement, measure


def test_measurement_records_latency():
    with measure() as m:
        time.sleep(0.01)
    assert m.latency_ms >= 10
    assert m.latency_ms < 100  # not absurdly slow


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
