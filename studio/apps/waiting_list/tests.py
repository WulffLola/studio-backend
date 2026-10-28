import pytest
from django.urls import reverse
from .models import WaitingList


@pytest.mark.django_db
class TestWaitingListSoftDelete:

    def test_delete_sets_deleted(self, person, slot):
        wl = WaitingList.objects.create(person=person, slot=slot)
        wl.delete()
        wl.refresh_from_db()
        assert wl.deleted is not None

    def test_objects_hides_deleted(self, person, slot):
        wl = WaitingList.objects.create(person=person, slot=slot)
        wl.delete()
        assert not WaitingList.objects.filter(pk=wl.pk).exists()

    def test_all_objects_includes_deleted(self, person, slot):
        wl = WaitingList.objects.create(person=person, slot=slot)
        wl.delete()
        assert WaitingList.all_objects.filter(pk=wl.pk).exists()

    def test_all_objects_dead_returns_deleted(self, person, slot):
        wl = WaitingList.objects.create(person=person, slot=slot)
        wl.delete()
        assert WaitingList.all_objects.dead().filter(pk=wl.pk).exists()

    def test_all_objects_alive_excludes_deleted(self, person, slot):
        wl = WaitingList.objects.create(person=person, slot=slot)
        wl.delete()
        assert not WaitingList.all_objects.alive().filter(pk=wl.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user, person, slot):
        wl = WaitingList.objects.create(person=person, slot=slot)
        wl.delete()
        qs = WaitingList.all_objects.for_user(admin_user)
        assert qs.filter(pk=wl.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user, person, slot):
        wl = WaitingList.objects.create(person=person, slot=slot)
        wl.delete()
        qs = WaitingList.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=wl.pk).exists()

    def test_restore(self, person, slot):
        wl = WaitingList.objects.create(person=person, slot=slot)
        wl.delete()
        wl.restore()
        wl.refresh_from_db()
        assert wl.deleted is None

    def test_hard_delete_removes_from_db(self, person, slot):
        wl = WaitingList.objects.create(person=person, slot=slot)
        pk = wl.pk
        wl.hard_delete()
        assert not WaitingList.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestWaitingListViewForUser:
    URL = 'waiting-list-list'

    def test_admin_list_includes_deleted(self, admin_client, person, slot):
        wl = WaitingList.objects.create(person=person, slot=slot)
        wl.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert wl.id in ids

    def test_consultor_list_excludes_deleted(self, consultor_client, person, slot):
        wl = WaitingList.objects.create(person=person, slot=slot)
        wl.delete()
        response = consultor_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert wl.id not in ids

    def test_delete_endpoint_is_soft_delete(self, admin_client, person, slot):
        wl = WaitingList.objects.create(person=person, slot=slot)
        url = reverse('waiting-list-detail', args=[wl.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert WaitingList.all_objects.filter(pk=wl.pk).exists()
        wl.refresh_from_db()
        assert wl.deleted is not None
