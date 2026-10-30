import pytest
from datetime import date, time, timedelta
from apps.recommendations.services import build_franjas, FranjaKey

@pytest.mark.django_db
def test_build_franjas_occupancy(room, person):
    from apps.slots.models import Slot
    from apps.appointments.models import Appointment
    d = date(2026, 8, 3)  # lunes
    s = Slot.objects.create(room=room, date=d, start_time=time(10, 0),
                            end_time=time(11, 0), availability=1)
    Appointment.objects.create(slot=s, person=person)              # confirmada -> cupos 2, occ 0.5
    cancelled = Appointment.objects.create(slot=s, person=person)  # cancelada no cuenta
    cancelled.deleted = date(2026, 8, 3); cancelled.save()
    franjas = build_franjas(date(2026, 8, 1), date(2026, 8, 31))
    key = FranjaKey(room.studio_id, room.id, None, 0, time(10, 0))
    assert franjas[key] == [0.5]
