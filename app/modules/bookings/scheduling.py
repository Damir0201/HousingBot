"""Pure scheduling logic: no DB, no I/O -> trivially unit-testable."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo


@dataclass(frozen=True, slots=True)
class Interval:
    start: datetime
    end: datetime

    def overlaps(self, other: "Interval", buffer: timedelta = timedelta(0)) -> bool:
        """Half-open intervals; `buffer` is the travel gap required between two viewings."""
        return self.start < other.end + buffer and other.start < self.end + buffer


@dataclass(frozen=True, slots=True)
class AgentSchedule:
    agent_id: int
    work_start: time
    work_end: time
    busy: tuple[Interval, ...] = field(default_factory=tuple)

    def working_window(self, day: date, tz: tzinfo) -> Interval:
        return Interval(datetime.combine(day, self.work_start, tz), datetime.combine(day, self.work_end, tz))

    def is_free(self, slot: Interval, day: date, tz: tzinfo, buffer: timedelta) -> bool:
        window = self.working_window(day, tz)
        if slot.start < window.start or slot.end > window.end:
            return False
        return not any(slot.overlaps(b, buffer) for b in self.busy)


def day_slots(day: date, start: time, end: time, slot_minutes: int, tz: tzinfo) -> list[Interval]:
    step = timedelta(minutes=slot_minutes)
    cursor = datetime.combine(day, start, tz)
    limit = datetime.combine(day, end, tz)
    slots: list[Interval] = []
    while cursor + step <= limit:
        slots.append(Interval(cursor, cursor + step))
        cursor += step
    return slots


def free_agents(
    slot: Interval,
    schedules: Sequence[AgentSchedule],
    day: date,
    tz: tzinfo,
    buffer: timedelta,
) -> list[int]:
    """Agents free for the slot, least loaded first (fair distribution between agents)."""
    candidates = [s for s in schedules if s.is_free(slot, day, tz, buffer)]
    candidates.sort(key=lambda s: (len(s.busy), s.agent_id))
    return [s.agent_id for s in candidates]


def available_slots(
    day: date,
    schedules: Sequence[AgentSchedule],
    *,
    slot_minutes: int,
    buffer: timedelta,
    tz: tzinfo,
    now: datetime,
    min_lead: timedelta = timedelta(minutes=30),
    client_busy: Iterable[Interval] = (),
) -> list[Interval]:
    if not schedules:
        return []
    start = min(s.work_start for s in schedules)
    end = max(s.work_end for s in schedules)
    earliest = now + min_lead
    client_busy = tuple(client_busy)
    result: list[Interval] = []
    for slot in day_slots(day, start, end, slot_minutes, tz):
        if slot.start < earliest:
            continue
        if any(slot.overlaps(b) for b in client_busy):
            continue
        if free_agents(slot, schedules, day, tz, buffer):
            result.append(slot)
    return result
