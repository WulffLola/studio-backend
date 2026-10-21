import pytest
from django.urls import reverse
from .models import Week


@pytest.mark.django_db
class TestWeekSoftDelete:

    def test_delete_sets_deleted(self):
        week = Week.objects.create(day='Lunes')
        week.delete()
        week.refresh_from_db()
        assert week.deleted is not None

    def test_objects_hides_deleted(self):
        week = Week.objects.create(day='Lunes')
        week.delete()
        assert not Week.objects.filter(pk=week.pk).exists()

    def test_all_objects_includes_deleted(self):
        week = Week.objects.create(day='Lunes')
        week.delete()
        assert Week.all_objects.filter(pk=week.pk).exists()

    def test_all_objects_dead_returns_deleted(self):
        week = Week.objects.create(day='Lunes')
        week.delete()
        assert Week.all_objects.dead().filter(pk=week.pk).exists()

    def test_all_objects_alive_excludes_deleted(self):
        week = Week.objects.create(day='Lunes')
        week.delete()
        assert not Week.all_objects.alive().filter(pk=week.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user):
        week = Week.objects.create(day='Lunes')
        week.delete()
        qs = Week.all_objects.for_user(admin_user)
        assert qs.filter(pk=week.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user):
        week = Week.objects.create(day='Lunes')
        week.delete()
        qs = Week.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=week.pk).exists()

    def test_restore(self):
        week = Week.objects.create(day='Lunes')
        week.delete()
        week.restore()
        week.refresh_from_db()
        assert week.deleted is None

    def test_hard_delete_removes_from_db(self):
        week = Week.objects.create(day='Lunes')
        pk = week.pk
        week.hard_delete()
        assert not Week.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestWeekViewForUser:
    URL = 'week-list'

    def test_admin_list_includes_deleted(self, admin_client):
        week = Week.objects.create(day='Martes')
        week.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert week.id in ids

    def test_consultor_list_excludes_deleted(self, consultor_client):
        week = Week.objects.create(day='Martes')
        week.delete()
        response = consultor_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert week.id not in ids

    def test_delete_endpoint_is_soft_delete(self, admin_client):
        week = Week.objects.create(day='Miercoles')
        url = reverse('week-detail', args=[week.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert Week.all_objects.filter(pk=week.pk).exists()
        week.refresh_from_db()
        assert week.deleted is not None
