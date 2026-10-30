import pytest
from datetime import date, time, timedelta
from django.utils import timezone
from apps.recommendations.services import (
    waitlist_count, compatible_rooms, has_conflict)


@pytest.mark.django_db
def test_waitlist_dedup(room, person):
    from apps.slots.models import Slot
    from apps.waiting_list.models import WaitingList
    d = date(2026, 8, 3)
    s = Slot.objects.create(room=room, date=d, start_time=time(10, 0), end_time=time(11, 0), availability=5)
    WaitingList.objects.create(person=person, slot=s)
    WaitingList.objects.create(person=person, slot=s)  # dup misma persona
    assert waitlist_count(room.studio_id, room.id, 0, time(10, 0), date(2026, 8, 1), date(2026, 8, 31)) == 1


@pytest.mark.django_db
def test_compatible_rooms_by_history(room, activity_subtype):
    from apps.slots.models import Slot
    Slot.objects.create(room=room, date=date(2026, 8, 3), start_time=time(10, 0),
                        end_time=time(11, 0), availability=5, activity_subtype=activity_subtype)
    rooms = compatible_rooms(room.studio_id, activity_subtype.id)
    assert room in rooms


def _future_monday():
    future = timezone.now().date() + timedelta(days=7)
    while future.weekday() != 0:
        future += timedelta(days=1)
    return future


@pytest.mark.django_db
def test_has_conflict_future_slot(room):
    from apps.slots.models import Slot
    Slot.objects.create(room=room, date=_future_monday(), start_time=time(10, 0), end_time=time(11, 0), availability=5)
    assert has_conflict(room.id, 0, time(10, 0), time(11, 0)) is True
    assert has_conflict(room.id, 0, time(12, 0), time(13, 0)) is False


@pytest.mark.django_db
def test_has_conflict_detects_range_overlap(room):
    from apps.slots.models import Slot
    Slot.objects.create(room=room, date=_future_monday(), start_time=time(9, 30), end_time=time(10, 30), availability=5)
    assert has_conflict(room.id, 0, time(9, 0), time(10, 0)) is True


@pytest.mark.django_db
def test_has_conflict_adjacent_slot_no_conflict(room):
    from apps.slots.models import Slot
    Slot.objects.create(room=room, date=_future_monday(), start_time=time(8, 0), end_time=time(9, 0), availability=5)
    assert has_conflict(room.id, 0, time(9, 0), time(10, 0)) is False


@pytest.mark.django_db
def test_has_conflict_null_end_time_same_start(room):
    from apps.slots.models import Slot
    Slot.objects.create(room=room, date=_future_monday(), start_time=time(9, 0), end_time=None, availability=5)
    assert has_conflict(room.id, 0, time(9, 0), time(10, 0)) is True
    assert has_conflict(room.id, 0, time(11, 0), time(12, 0)) is False
