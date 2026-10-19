import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from .models import Room


@pytest.mark.django_db
class TestRoomSoftDelete:

    def test_delete_sets_deleted(self, studio):
        room = Room.objects.create(name='Sala A', studio=studio)
        room.delete()
        room.refresh_from_db()
        assert room.deleted is not None

    def test_objects_hides_deleted(self, studio):
        room = Room.objects.create(name='Sala A', studio=studio)
        room.delete()
        assert not Room.objects.filter(pk=room.pk).exists()

    def test_all_objects_includes_deleted(self, studio):
        room = Room.objects.create(name='Sala A', studio=studio)
        room.delete()
        assert Room.all_objects.filter(pk=room.pk).exists()

    def test_all_objects_dead_returns_deleted(self, studio):
        room = Room.objects.create(name='Sala A', studio=studio)
        room.delete()
        assert Room.all_objects.dead().filter(pk=room.pk).exists()

    def test_all_objects_alive_excludes_deleted(self, studio):
        room = Room.objects.create(name='Sala A', studio=studio)
        room.delete()
        assert not Room.all_objects.alive().filter(pk=room.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user, studio):
        room = Room.objects.create(name='Sala A', studio=studio)
        room.delete()
        qs = Room.all_objects.for_user(admin_user)
        assert qs.filter(pk=room.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user, studio):
        room = Room.objects.create(name='Sala A', studio=studio)
        room.delete()
        qs = Room.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=room.pk).exists()

    def test_restore(self, studio):
        room = Room.objects.create(name='Sala A', studio=studio)
        room.delete()
        room.restore()
        room.refresh_from_db()
        assert room.deleted is None

    def test_hard_delete_removes_from_db(self, studio):
        room = Room.objects.create(name='Sala A', studio=studio)
        pk = room.pk
        room.hard_delete()
        assert not Room.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestRoomViewForUser:
    URL = 'rooms-list'

    def test_admin_list_includes_deleted(self, admin_client, studio):
        room = Room.objects.create(name='Sala B', studio=studio)
        room.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert room.id in ids

    def test_consultor_list_excludes_deleted(self, consultor_client, studio):
        room = Room.objects.create(name='Sala B', studio=studio)
        room.delete()
        response = consultor_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert room.id not in ids

    def test_delete_endpoint_is_soft_delete(self, admin_client, studio):
        room = Room.objects.create(name='Sala C', studio=studio)
        url = reverse('rooms-detail', args=[room.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert Room.all_objects.filter(pk=room.pk).exists()
        room.refresh_from_db()
        assert room.deleted is not None


@pytest.mark.django_db
class TestRoomRequiresAuth:
    """Un request sin autenticar debe devolver 401 (credenciales no provistas),
    no un 500 por explotar en get_queryset() con AnonymousUser."""

    def test_anonymous_list_returns_401(self):
        client = APIClient()
        response = client.get(reverse('rooms-list'))
        assert response.status_code == 401
        assert response.data['detail'] == 'Authentication credentials were not provided.'

    def test_anonymous_detail_returns_401(self, studio):
        room = Room.objects.create(name='Sala H', studio=studio)
        client = APIClient()
        response = client.get(reverse('rooms-detail', args=[room.pk]))
        assert response.status_code == 401

    def test_anonymous_cannot_create(self, studio):
        client = APIClient()
        response = client.post(
            reverse('rooms-list'),
            data={'name': 'Sala anónima', 'studio': studio.pk},
            format='json',
        )
        assert response.status_code == 401
        assert not Room.objects.filter(name='Sala anónima').exists()


@pytest.mark.django_db
class TestRoomDeletedSerializerField:
    """El serializer expone `deleted` para poder ver el estado y dar de alta
    (restore) vía API, igual que en el resto de los modelos."""

    def test_get_exposes_deleted_field(self, admin_client, studio):
        room = Room.objects.create(name='Sala D', studio=studio)
        url = reverse('rooms-detail', args=[room.pk])
        response = admin_client.get(url)
        assert response.status_code == 200
        assert 'deleted' in response.data
        assert response.data['deleted'] is None

    def test_get_exposes_deleted_date_when_deleted(self, admin_client, studio):
        room = Room.objects.create(name='Sala F', studio=studio)
        room.delete()
        url = reverse('rooms-detail', args=[room.pk])
        response = admin_client.get(url)
        assert response.status_code == 200
        assert response.data['deleted'] is not None

    def test_patch_deleted_null_restores(self, admin_client, studio):
        room = Room.objects.create(name='Sala E', studio=studio)
        room.delete()
        url = reverse('rooms-detail', args=[room.pk])
        response = admin_client.patch(url, {'deleted': None}, format='json')
        assert response.status_code == 200
        assert response.data['deleted'] is None
        room.refresh_from_db()
        assert room.deleted is None
        assert Room.objects.filter(pk=room.pk).exists()

    def test_consultor_cannot_restore_deleted(self, consultor_client, studio):
        room = Room.objects.create(name='Sala G', studio=studio)
        room.delete()
        url = reverse('rooms-detail', args=[room.pk])
        response = consultor_client.patch(url, {'deleted': None}, format='json')
        assert response.status_code == 404
        room.refresh_from_db()
        assert room.deleted is not None
