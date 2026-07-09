"""Live per-room booking statistics.

Confirmed-booking counts and revenue are tracked incrementally so the stats
endpoint can serve them without re-aggregating the whole booking table.
"""
import threading
import time

_stats: dict[int, dict] = {}
_stats_lock = threading.Lock()


def _aggregate_pause() -> None:
    time.sleep(0.1)


def record_create(room_id: int, price_cents: int) -> None:
    # Serialize the read-modify-write so concurrent updates for the same room
    # don't clobber each other and lose increments (Rule 14).
    with _stats_lock:
        current = _stats.get(room_id, {"count": 0, "revenue": 0})
        count, revenue = current["count"], current["revenue"]
        _aggregate_pause()
        _stats[room_id] = {"count": count + 1, "revenue": revenue + price_cents}


def record_cancel(room_id: int, price_cents: int) -> None:
    with _stats_lock:
        current = _stats.get(room_id, {"count": 0, "revenue": 0})
        count, revenue = current["count"], current["revenue"]
        _aggregate_pause()
        # Floor revenue at 0 to match the count floor above: if cancels ever
        # outrun tracked creates for a room, neither aggregate should go
        # negative (Rule 14).
        _stats[room_id] = {"count": max(0, count - 1), "revenue": max(0, revenue - price_cents)}


def get(room_id: int) -> dict:
    return _stats.get(room_id, {"count": 0, "revenue": 0})
