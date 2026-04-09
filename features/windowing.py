from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Iterator, List, Sequence

from data.schema import RawEvent, WindowConfig


@dataclass
class EventWindow:
    user_id: str
    start: datetime
    end: datetime
    events: List[RawEvent]
    window_size_seconds: int
    step_seconds: int


def floor_to_minute(timestamp: datetime) -> datetime:
    return timestamp.replace(second=0, microsecond=0)


def ceil_to_minute(timestamp: datetime) -> datetime:
    floored = floor_to_minute(timestamp)
    if timestamp == floored:
        return floored
    return floored + timedelta(minutes=1)


def iter_sliding_windows(
    user_id: str,
    events: Sequence[RawEvent],
    config: WindowConfig | None = None,
    include_partial: bool = False,
) -> Iterator[EventWindow]:
    """
    Yield 5-minute windows advanced every 1 minute.

    Window membership rule is (start, end] to avoid duplicate attribution on
    exact minute boundaries.
    """
    if not events:
        return

    cfg = config or WindowConfig()
    ordered = sorted(events, key=lambda item: item.timestamp)

    step_delta = timedelta(minutes=cfg.step_minutes)
    window_delta = timedelta(minutes=cfg.window_minutes)

    first_event_ts = ordered[0].timestamp
    last_event_ts = ordered[-1].timestamp

    if include_partial:
        window_end = ceil_to_minute(first_event_ts)
    else:
        window_end = floor_to_minute(first_event_ts) + window_delta
    final_window_end = ceil_to_minute(last_event_ts)

    n_events = len(ordered)
    left = 0
    right = 0

    while window_end <= final_window_end:
        window_start = window_end - window_delta
        if include_partial and window_start < first_event_ts:
            window_start = first_event_ts

        while left < n_events and ordered[left].timestamp <= window_start:
            left += 1
        while right < n_events and ordered[right].timestamp <= window_end:
            right += 1

        yield EventWindow(
            user_id=user_id,
            start=window_start,
            end=window_end,
            events=ordered[left:right],
            window_size_seconds=cfg.window_seconds,
            step_seconds=cfg.step_seconds,
        )

        window_end += step_delta
