import pytest
from django.urls import reverse
from .models import Hour


@pytest.mark.django_db
class TestHourSoftDelete:

    def test_delete_sets_deleted(self, teacher):
        hour = Hour.objects.create(teacher=teacher, month='01', hour='8', total='1000', left='1000')
        hour.delete()
        hour.refresh_from_db()
        assert hour.deleted is not None

    def test_objects_hides_deleted(self, teacher):
        hour = Hour.objects.create(teacher=teacher, month='01', hour='8', total='1000', left='1000')
        hour.delete()
        assert not Hour.objects.filter(pk=hour.pk).exists()

    def test_all_objects_includes_deleted(self, teacher):
        hour = Hour.objects.create(teacher=teacher, month='01', hour='8', total='1000', left='1000')
        hour.delete()
        assert Hour.all_objects.filter(pk=hour.pk).exists()

    def test_all_objects_dead_returns_deleted(self, teacher):
        hour = Hour.objects.create(teacher=teacher, month='01', hour='8', total='1000', left='1000')
        hour.delete()
        assert Hour.all_objects.dead().filter(pk=hour.pk).exists()

    def test_all_objects_alive_excludes_deleted(self, teacher):
        hour = Hour.objects.create(teacher=teacher, month='01', hour='8', total='1000', left='1000')
        hour.delete()
        assert not Hour.all_objects.alive().filter(pk=hour.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user, teacher):
        hour = Hour.objects.create(teacher=teacher, month='01', hour='8', total='1000', left='1000')
        hour.delete()
        qs = Hour.all_objects.for_user(admin_user)
        assert qs.filter(pk=hour.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user, teacher):
        hour = Hour.objects.create(teacher=teacher, month='01', hour='8', total='1000', left='1000')
        hour.delete()
        qs = Hour.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=hour.pk).exists()

    def test_restore(self, teacher):
        hour = Hour.objects.create(teacher=teacher, month='01', hour='8', total='1000', left='1000')
        hour.delete()
        hour.restore()
        hour.refresh_from_db()
        assert hour.deleted is None

    def test_hard_delete_removes_from_db(self, teacher):
        hour = Hour.objects.create(teacher=teacher, month='01', hour='8', total='1000', left='1000')
        pk = hour.pk
        hour.hard_delete()
        assert not Hour.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestHourViewForUser:
    URL = 'hour_view-list'

    def test_admin_list_includes_deleted(self, admin_client, teacher):
        hour = Hour.objects.create(teacher=teacher, month='02', hour='8', total='2000', left='2000')
        hour.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert hour.id in ids

    def test_consultor_cannot_access(self, consultor_client):
        response = consultor_client.get(reverse(self.URL))
        assert response.status_code == 403

    def test_delete_endpoint_is_soft_delete(self, admin_client, teacher):
        hour = Hour.objects.create(teacher=teacher, month='03', hour='8', total='3000', left='3000')
        url = reverse('hour_view-detail', args=[hour.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert Hour.all_objects.filter(pk=hour.pk).exists()
        hour.refresh_from_db()
        assert hour.deleted is not None
