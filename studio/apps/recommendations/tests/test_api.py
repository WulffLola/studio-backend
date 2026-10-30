import pytest
from datetime import time, timedelta
from django.urls import reverse
from django.utils import timezone


def _make(room, person, n, confirmed, availability, activity_subtype):
    from apps.slots.models import Slot
    from apps.appointments.models import Appointment
    d = timezone.now().date() - timedelta(days=1)
    while d.weekday() != 0:
        d -= timedelta(days=1)
    for _ in range(n):
        s = Slot.objects.create(room=room, date=d, start_time=time(10, 0), end_time=time(11, 0),
                                availability=availability, activity_subtype=activity_subtype)
        for _ in range(confirmed):
            Appointment.objects.create(slot=s, person=person)
        d -= timedelta(days=7)


@pytest.mark.django_db
def test_analyze_creates_recommendations(admin_client, room, person, activity_subtype):
    _make(room, person, 8, 5, 0, activity_subtype)
    resp = admin_client.post(reverse('recommendations-analyze'), {}, format='json')
    assert resp.status_code == 201
    assert resp.data['recommendations']
    lst = admin_client.get(reverse('recommendations-list'))
    assert lst.status_code == 200
    assert len(lst.data) >= 1


@pytest.mark.django_db
def test_analyze_invalid_param_400(admin_client):
    resp = admin_client.post(reverse('recommendations-analyze'), {'window_weeks': 50}, format='json')
    assert resp.status_code == 400


@pytest.mark.django_db
def test_requires_admin(client, room):
    resp = client.post(reverse('recommendations-analyze'), {}, format='json')
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_analyze_returns_summary(admin_client, room, person, activity_subtype):
    _make(room, person, 8, 5, 0, activity_subtype)
    resp = admin_client.post(reverse('recommendations-analyze'), {}, format='json')
    assert resp.status_code == 201
    summary = resp.data['summary']
    assert summary['franjas_analizadas'] >= 1
    assert summary['generadas'] >= 1
    assert summary['insuficientes'] == 0


@pytest.mark.django_db
def test_analyze_summary_insufficient(admin_client, room, person, activity_subtype):
    _make(room, person, 3, 5, 0, activity_subtype)
    resp = admin_client.post(reverse('recommendations-analyze'), {}, format='json')
    assert resp.data['summary']['insuficientes'] >= 1
    assert resp.data['summary']['generadas'] == 0
