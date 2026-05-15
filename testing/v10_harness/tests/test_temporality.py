from datetime import datetime, timezone
from testing.v10_harness.temporality import NowAnchor


def test_now_anchor_freezes_a_single_timestamp():
    anchor = NowAnchor.lock_from_value(datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc))
    assert anchor.now() == datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
    # Repeated calls return the same value
    assert anchor.now() == anchor.now()


def test_now_anchor_parameterizes_sql_with_now_marker():
    anchor = NowAnchor.lock_from_value(datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc))
    sql = "SELECT COUNT(*) FROM `case` WHERE createdAt >= :now"
    bound = anchor.bind_sql(sql)
    assert bound["sql"] == "SELECT COUNT(*) FROM `case` WHERE createdAt >= %(now)s"
    assert bound["params"] == {"now": datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)}


def test_now_anchor_handles_no_now_marker():
    anchor = NowAnchor.lock_from_value(datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc))
    sql = "SELECT COUNT(*) FROM `case`"
    bound = anchor.bind_sql(sql)
    assert bound["sql"] == "SELECT COUNT(*) FROM `case`"
    assert bound["params"] == {}
