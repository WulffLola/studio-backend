import pytest
from django.urls import reverse
from apps.plans_subtype.models import PlansSubtype


@pytest.mark.django_db
class TestActivitySubTypeExposesPlansSubtypes:
    """El endpoint /activity-subtype/ expone los plans_subtype de cada
    subactividad (relación reversa), para que el front los vea."""

    def test_detail_exposes_plans_subtypes(self, admin_client, activity_subtype, plans_subtype_a):
        url = reverse('activity-subtype-detail', args=[activity_subtype.pk])
        response = admin_client.get(url)
        assert response.status_code == 200
        assert 'plans_subtypes' in response.data
        ids = [ps['id'] for ps in response.data['plans_subtypes']]
        assert plans_subtype_a.id in ids
        item = next(ps for ps in response.data['plans_subtypes'] if ps['id'] == plans_subtype_a.id)
        assert item['name'] == plans_subtype_a.name
        assert item['plan_type_name'] == plans_subtype_a.plan_type.name

    def test_plans_subtypes_empty_when_none(self, admin_client, activity_subtype):
        url = reverse('activity-subtype-detail', args=[activity_subtype.pk])
        response = admin_client.get(url)
        assert response.status_code == 200
        assert response.data['plans_subtypes'] == []

    def test_deleted_plans_subtype_excluded(self, admin_client, activity_subtype, plans_type):
        ps = PlansSubtype.objects.create(name='Borrado', plan_type=plans_type, activity_subtype=activity_subtype)
        ps.delete()
        url = reverse('activity-subtype-detail', args=[activity_subtype.pk])
        response = admin_client.get(url)
        assert response.status_code == 200
        ids = [p['id'] for p in response.data['plans_subtypes']]
        assert ps.id not in ids
