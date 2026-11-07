import pytest
from datetime import date, time, timedelta
from django.utils import timezone
from apps.recommendations.services import run_analysis, default_params


def _make_past_mondays(room, person, n, confirmed, availability, activity_subtype=None):
    from apps.slots.models import Slot
    from apps.appointments.models import Appointment
    today = timezone.now().date()
    d = today - timedelta(days=1)
    while d.weekday() != 0:
        d -= timedelta(days=1)
    made = 0
    while made < n:
        s = Slot.objects.create(room=room, date=d, start_time=time(10, 0), end_time=time(11, 0),
                                availability=availability, activity_subtype=activity_subtype)
        for _ in range(confirmed):
            Appointment.objects.create(slot=s, person=person)
        d -= timedelta(days=7)
        made += 1


@pytest.mark.django_db
def test_run_analysis_high_demand_creates_add(room, person, activity_subtype):
    # 8 clases llenas (availability 0, 5 confirmadas) -> alta demanda
    _make_past_mondays(room, person, n=8, confirmed=5, availability=0, activity_subtype=activity_subtype)
    analysis = run_analysis(default_params())
    recs = analysis.recommendations.all()
    assert recs.filter(type='add').count() == 1
    r = recs.get(type='add')
    assert r.observations_count == 8
    assert r.weekday == 0 and r.start_time == time(10, 0)


@pytest.mark.django_db
def test_dedup_against_previous_pending(room, person, activity_subtype):
    _make_past_mondays(room, person, n=8, confirmed=5, availability=0, activity_subtype=activity_subtype)
    run_analysis(default_params())
    a2 = run_analysis(default_params())
    # la 2a corrida no vuelve a crear una add pendiente identica
    assert a2.recommendations.filter(type='add').count() == 0


@pytest.mark.django_db
def test_insufficient_no_recommendation(room, person, activity_subtype):
    _make_past_mondays(room, person, n=5, confirmed=5, availability=0, activity_subtype=activity_subtype)
    analysis = run_analysis(default_params())
    assert analysis.recommendations.count() == 0


@pytest.mark.django_db
def test_add_alternative_with_room_capacity_none(room, person, activity_subtype):
    assert room.capacity is None
    _make_past_mondays(room, person, n=8, confirmed=5, availability=0, activity_subtype=activity_subtype)
    analysis = run_analysis(default_params())
    r = analysis.recommendations.get(type='add')
    assert r.proposed_alternative is not None
    assert 'sin_sala_alternativa' not in r.pending_conditions
    assert analysis.run_summary['generadas'] == 1


def _make_past_slot(room, weekday, start, end, activity_subtype, availability=5, weeks_back=1):
    from apps.slots.models import Slot
    d = timezone.now().date() - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    d -= timedelta(weeks=weeks_back - 1)
    return Slot.objects.create(room=room, date=d, start_time=start, end_time=end,
                               availability=availability, activity_subtype=activity_subtype)


@pytest.mark.django_db
def test_low_without_demand_elsewhere_is_reduce(room, person, activity_subtype):
    _make_past_mondays(room, person, n=8, confirmed=0, availability=5, activity_subtype=activity_subtype)
    analysis = run_analysis(default_params())
    assert analysis.recommendations.filter(type='reduce').count() == 1
    assert analysis.recommendations.filter(type='relocate').count() == 0


@pytest.mark.django_db
def test_low_with_waitlist_in_other_franja_is_relocate(room, person, activity_subtype):
    from apps.waiting_list.models import WaitingList
    _make_past_mondays(room, person, n=8, confirmed=0, availability=5, activity_subtype=activity_subtype)
    other = _make_past_slot(room, 1, time(18, 0), time(19, 0), activity_subtype)  # martes 18:00
    WaitingList.objects.create(person=person, slot=other)
    analysis = run_analysis(default_params())
    r = analysis.recommendations.get(type='relocate', weekday=0)
    assert r.proposed_alternative is not None
    assert r.proposed_alternative['weekday'] == 1
    assert r.proposed_alternative['start_time'] == '18:00:00'
    assert r.proposed_alternative['room_id'] == room.id
    assert r.proposed_alternative['is_new_slot'] is True


@pytest.mark.django_db
def test_low_with_high_occupancy_in_other_franja_is_relocate(room, person, activity_subtype):
    _make_past_mondays(room, person, n=8, confirmed=0, availability=5, activity_subtype=activity_subtype)
    from apps.slots.models import Slot
    from apps.appointments.models import Appointment
    for w in range(1, 9):
        s = _make_past_slot(room, 2, time(18, 0), time(19, 0), activity_subtype, availability=0, weeks_back=w)
        Appointment.objects.create(slot=s, person=person)
    analysis = run_analysis(default_params())
    r = analysis.recommendations.get(type='relocate', weekday=0)
    assert r.proposed_alternative['weekday'] == 2


@pytest.mark.django_db
def test_own_waitlist_no_longer_triggers_relocate(room, person, activity_subtype):
    from apps.slots.models import Slot
    from apps.waiting_list.models import WaitingList
    _make_past_mondays(room, person, n=8, confirmed=0, availability=5, activity_subtype=activity_subtype)
    WaitingList.objects.create(person=person, slot=Slot.objects.filter(room=room).first())
    analysis = run_analysis(default_params())
    assert analysis.recommendations.filter(type='relocate').count() == 0
    # con lista de espera propia no se recomienda reducir (D5, HU-19 c.3)
    assert analysis.recommendations.filter(type='reduce').count() == 0
    assert len(analysis.run_summary['baja_con_lista_de_espera']) == 1


@pytest.mark.django_db
def test_alternative_respects_room_capacity(room, person, activity_subtype):
    from apps.rooms.models import Room
    room.capacity = 5
    room.save()
    _make_past_mondays(room, person, n=8, confirmed=10, availability=0, activity_subtype=activity_subtype)
    analysis = run_analysis(default_params())
    # unica sala (cap 5) < cupos 10: sin recurso no hay recomendacion «add» (D2),
    # la alta demanda queda en el resumen del analisis
    assert analysis.recommendations.filter(type='add').count() == 0
    assert len(analysis.run_summary['alta_demanda_sin_recurso']) == 1
    # sala grande que aloja la actividad -> se propone
    big = Room.objects.create(name='Sala grande', studio=room.studio, capacity=12)
    _make_past_slot(big, 3, time(7, 0), time(8, 0), activity_subtype)
    analysis = run_analysis(default_params())
    r = analysis.recommendations.get(type='add')
    assert r.proposed_alternative['room_id'] == big.id


@pytest.mark.django_db
@pytest.mark.parametrize('state', ['accepted', 'discarded'])
def test_dedup_against_decided_recommendations(room, person, activity_subtype, state):
    _make_past_mondays(room, person, n=8, confirmed=5, availability=0, activity_subtype=activity_subtype)
    a1 = run_analysis(default_params())
    r = a1.recommendations.get(type='add')
    r.state = state
    r.save()
    a2 = run_analysis(default_params())
    assert a2.recommendations.filter(type='add').count() == 0


@pytest.mark.django_db
def test_relocate_degrades_to_reduce_without_free_compatible_room(room, person, activity_subtype):
    from apps.waiting_list.models import WaitingList
    room.capacity = 1  # insuficiente para cupos=5 del origen
    room.save()
    _make_past_mondays(room, person, n=8, confirmed=0, availability=5, activity_subtype=activity_subtype)
    other = _make_past_slot(room, 1, time(18, 0), time(19, 0), activity_subtype)
    WaitingList.objects.create(person=person, slot=other)
    analysis = run_analysis(default_params())
    assert analysis.recommendations.filter(type='relocate').count() == 0
    r = analysis.recommendations.get(type='reduce', weekday=0)
    assert r.proposed_alternative is None
