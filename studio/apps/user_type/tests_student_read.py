import pytest
from django.urls import reverse


READ_ENDPOINTS = [
    'slots-list', 'fixed-slots-list', 'activity-type-list', 'activity-subtype-list',
    'teachers-list', 'plans-type-list', 'plans-subtype-list', 'combo-plan-discount-list',
    'studios-list', 'rooms-list', 'home-phrase-list',
]


@pytest.mark.django_db
@pytest.mark.parametrize('basename', READ_ENDPOINTS)
def test_student_can_get(basename, student_client):
    resp = student_client.get(reverse(basename))
    assert resp.status_code == 200, f"{basename}: {resp.status_code}"


@pytest.mark.django_db
def test_student_cannot_write_teacher(student_client):
    resp = student_client.post(reverse('teachers-list'), data={
        'name': 'X', 'last_name': 'Y', 'dni': '55555555',
    }, format='json')
    assert resp.status_code == 403


@pytest.mark.django_db
def test_student_cannot_write_studio(student_client):
    resp = student_client.post(reverse('studios-list'), data={'name': 'Z'}, format='json')
    assert resp.status_code == 403


@pytest.mark.django_db
def test_anonymous_still_blocked_on_slots(client):
    from django.urls import reverse
    resp = client.get(reverse('slots-list'))
    assert resp.status_code in (401, 403)
