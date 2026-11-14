from datetime import datetime
from zoneinfo import ZoneInfo

from app import scheduler
from app.models import Schedule


def test_trigger_next_fire_weekdays():
    s = Schedule(id=1, action="wake", time="07:30", weekdays="mon,tue,wed,thu,fri", enabled=True)
    tz = ZoneInfo("Europe/Berlin")
    # Samstag, 14.11.2026 -> nächster Termin Montag 16.11. 07:30
    start = datetime(2026, 11, 14, 22, 0, tzinfo=tz)
    nxt = scheduler.make_trigger(s).get_next_fire_time(None, start)
    assert nxt == datetime(2026, 11, 16, 7, 30, tzinfo=tz)


def test_next_run_none_when_disabled():
    s = Schedule(id=1, action="wake", time="07:30", weekdays="mon", enabled=False)
    assert scheduler.next_run(s) is None


def test_weekday_text():
    assert Schedule(weekdays="mon,tue,wed,thu,fri").weekday_text == "Mo–Fr"
    assert Schedule(weekdays="mon,tue,wed,thu,fri,sat,sun").weekday_text == "täglich"
    assert Schedule(weekdays="mon,wed").weekday_text == "Mo, Mi"
