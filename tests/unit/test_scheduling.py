from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.modules.bookings.scheduling import (
    AgentSchedule,
    Interval,
    available_slots,
    day_slots,
    free_agents,
)

TZ = ZoneInfo("Europe/Rome")
DAY = date(2026, 11, 10)


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 10, hour, minute, tzinfo=TZ)


def test_day_slots_generation() -> None:
    slots = day_slots(DAY, time(9, 0), time(11, 0), slot_minutes=30, tz=TZ)
    assert len(slots) == 4
    assert slots[0] == Interval(dt(9, 0), dt(9, 30))
    assert slots[-1] == Interval(dt(10, 30), dt(11, 0))


def test_interval_overlap_with_buffer() -> None:
    first = Interval(dt(10, 0), dt(10, 30))
    immediately_after = Interval(dt(10, 30), dt(11, 0))
    after_buffer = Interval(dt(10, 45), dt(11, 15))

    assert not first.overlaps(immediately_after, buffer=timedelta(0))
    assert first.overlaps(immediately_after, buffer=timedelta(minutes=15))
    assert not first.overlaps(after_buffer, buffer=timedelta(minutes=15))


def test_free_agents_distributes_by_least_busy_then_id() -> None:
    slot = Interval(dt(14, 0), dt(14, 30))
    schedules = [
        AgentSchedule(
            agent_id=1,
            work_start=time(9, 0),
            work_end=time(20, 0),
            busy=(Interval(dt(10, 0), dt(10, 30)), Interval(dt(11, 0), dt(11, 30))),
        ),
        AgentSchedule(
            agent_id=2,
            work_start=time(9, 0),
            work_end=time(20, 0),
            busy=(Interval(dt(10, 0), dt(10, 30)),),
        ),
        AgentSchedule(
            agent_id=3,
            work_start=time(9, 0),
            work_end=time(20, 0),
            busy=(Interval(dt(14, 0), dt(14, 30)),),  # busy during the target slot
        ),
    ]
    candidates = free_agents(slot, schedules, DAY, TZ, buffer=timedelta(minutes=15))
    # Agent 3 is busy; Agent 2 has 1 viewing vs Agent 1's 2 viewings -> [2, 1]
    assert candidates == [2, 1]


def test_available_slots_filters_past_and_client_conflicts() -> None:
    schedules = [
        AgentSchedule(
            agent_id=1,
            work_start=time(9, 0),
            work_end=time(11, 0),
            busy=(Interval(dt(10, 0), dt(10, 30)),),
        )
    ]
    slots = available_slots(
        DAY,
        schedules,
        slot_minutes=30,
        buffer=timedelta(minutes=15),
        tz=TZ,
        now=dt(8, 45),  # +30m lead time => earliest slot >= 09:15
        client_busy=[Interval(dt(9, 30), dt(10, 0))],
    )
    # 09:00 is before now+30m; 09:30 conflicts with client_busy AND buffer before 10:00;
    # 10:00 is agent busy; 10:30 conflicts with 15m buffer after 10:00-10:30.
    assert slots == []
