import pytest
from datetime import time
from django.urls import reverse
from rest_framework.test import APIClient
from .models import Studio


@pytest.mark.django_db
class TestStudioSoftDelete:

    def test_delete_sets_deleted(self):
        studio = Studio.objects.create(name='Studio Palermo')
        studio.delete()
        studio.refresh_from_db()
        assert studio.deleted is not None

    def test_objects_hides_deleted(self):
        studio = Studio.objects.create(name='Studio Palermo')
        studio.delete()
        assert not Studio.objects.filter(pk=studio.pk).exists()

    def test_all_objects_includes_deleted(self):
        studio = Studio.objects.create(name='Studio Palermo')
        studio.delete()
        assert Studio.all_objects.filter(pk=studio.pk).exists()

    def test_all_objects_dead_returns_deleted(self):
        studio = Studio.objects.create(name='Studio Palermo')
        studio.delete()
        assert Studio.all_objects.dead().filter(pk=studio.pk).exists()

    def test_all_objects_alive_excludes_deleted(self):
        studio = Studio.objects.create(name='Studio Palermo')
        studio.delete()
        assert not Studio.all_objects.alive().filter(pk=studio.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user):
        studio = Studio.objects.create(name='Studio Palermo')
        studio.delete()
        qs = Studio.all_objects.for_user(admin_user)
        assert qs.filter(pk=studio.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user):
        studio = Studio.objects.create(name='Studio Palermo')
        studio.delete()
        qs = Studio.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=studio.pk).exists()

    def test_restore(self):
        studio = Studio.objects.create(name='Studio Palermo')
        studio.delete()
        studio.restore()
        studio.refresh_from_db()
        assert studio.deleted is None

    def test_hard_delete_removes_from_db(self):
        studio = Studio.objects.create(name='Studio Palermo')
        pk = studio.pk
        studio.hard_delete()
        assert not Studio.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestStudioRequiresAuth:
    """Un request sin autenticar debe devolver 401 (credenciales no provistas),
    no un 500 por explotar en get_queryset() con AnonymousUser."""

    def test_anonymous_list_returns_401(self):
        client = APIClient()
        response = client.get(reverse('studios-list'))
        assert response.status_code == 401
        assert response.data['detail'] == 'Authentication credentials were not provided.'

    def test_anonymous_detail_returns_401(self, studio):
        client = APIClient()
        response = client.get(reverse('studios-detail', args=[studio.pk]))
        assert response.status_code == 401

    def test_anonymous_cannot_create(self):
        client = APIClient()
        response = client.post(
            reverse('studios-list'),
            data={'name': 'Estudio anónimo'},
            format='json',
        )
        assert response.status_code == 401
        assert not Studio.objects.filter(name='Estudio anónimo').exists()


@pytest.mark.django_db
class TestStudioViewForUser:
    URL = 'studios-list'

    def test_admin_list_includes_deleted(self, admin_client):
        studio = Studio.objects.create(name='Studio Belgrano')
        studio.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert studio.id in ids

    def test_consultor_list_excludes_deleted(self, consultor_client):
        studio = Studio.objects.create(name='Studio Belgrano')
        studio.delete()
        response = consultor_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert studio.id not in ids

    def test_delete_endpoint_is_soft_delete(self, admin_client):
        studio = Studio.objects.create(name='Studio Nuñez')
        url = reverse('studios-detail', args=[studio.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert Studio.all_objects.filter(pk=studio.pk).exists()
        studio.refresh_from_db()
        assert studio.deleted is not None


@pytest.mark.django_db
class TestStudioIsReady:
    """is_ready es calculado: True solo cuando el estudio tiene los 8 requisitos.

    Salas / slot templates / slots se cuentan por-estudio (vía room.studio);
    payment methods, activity types/subtypes y plans type/subtype son globales.
    """

    def test_empty_studio_is_not_ready(self):
        studio = Studio.objects.create(name='Studio Centro')
        assert studio.is_ready is False
        # todos los requisitos en False
        assert not any(studio.config_status().values())

    def test_becomes_ready_only_when_all_present(self):
        from apps.rooms.models import Room
        from apps.slots.models import SlotTemplate, Slot
        from apps.payment_method.models import PaymentMethod
        from apps.activity_type.models import ActivityType
        from apps.activity_subtype.models import ActivitySubType
        from apps.plans_type.models import PlansType
        from apps.plans_subtype.models import PlansSubtype

        studio = Studio.objects.create(name='Studio Centro')
        assert studio.is_ready is False

        # 1) sala (por-estudio)
        room = Room.objects.create(studio=studio, name='Sala 1', capacity=10)
        assert studio.is_ready is False
        # 2) slot template (vía room del estudio)
        SlotTemplate.objects.create(start_time=time(9, 0), end_time=time(10, 0), availability=10, room=room)
        assert studio.is_ready is False
        # 3) slot (vía room del estudio)
        Slot.objects.create(room=room)
        assert studio.is_ready is False
        # 4) payment method (global)
        PaymentMethod.objects.create(method='Efectivo')
        assert studio.is_ready is False
        # 5) activity type (global)
        at = ActivityType.objects.create(name='Pilates')
        assert studio.is_ready is False
        # 6) activity subtype (global)
        ast = ActivitySubType.objects.create(name='Reformer', activity_type=at)
        assert studio.is_ready is False
        # 7) plans type (global)
        pt = PlansType.objects.create(name='Mensual')
        assert studio.is_ready is False
        # 8) plans subtype (global) -> ahora sí, completo
        PlansSubtype.objects.create(name='4 clases', plan_type=pt, activity_subtype=ast)
        assert studio.is_ready is True

    def test_rooms_are_scoped_per_studio(self):
        """Las salas de OTRO estudio no cuentan para este."""
        from apps.rooms.models import Room
        s1 = Studio.objects.create(name='Estudio A')
        s2 = Studio.objects.create(name='Estudio B')
        Room.objects.create(studio=s2, name='Sala 1', capacity=10)
        assert s1.config_status()['rooms'] is False

    def test_soft_deleted_room_does_not_count(self):
        from apps.rooms.models import Room
        studio = Studio.objects.create(name='Studio Centro')
        room = Room.objects.create(studio=studio, name='Sala 1', capacity=10)
        assert studio.config_status()['rooms'] is True
        room.delete()  # baja lógica
        assert studio.config_status()['rooms'] is False


@pytest.mark.django_db
class TestStudioIsReadyReadOnly:
    """is_ready no se puede forzar manualmente desde la API."""

    def test_patch_is_ready_is_ignored(self, admin_client):
        studio = Studio.objects.create(name='Studio Centro')
        url = reverse('studios-detail', args=[studio.pk])
        response = admin_client.patch(url, {'is_ready': True}, format='json')
        assert response.status_code == 200
        assert response.data['is_ready'] is False
        studio.refresh_from_db()
        assert studio.is_ready is False


@pytest.mark.django_db
class TestStudioDeletedSerializerField:
    """El serializer expone `deleted` para poder ver el estado y dar de alta
    (restore) vía API, igual que en el resto de los modelos."""

    def test_get_exposes_deleted_field(self, admin_client):
        studio = Studio.objects.create(name='Studio Caballito')
        url = reverse('studios-detail', args=[studio.pk])
        response = admin_client.get(url)
        assert response.status_code == 200
        assert 'deleted' in response.data
        assert response.data['deleted'] is None

    def test_get_exposes_deleted_date_when_deleted(self, admin_client):
        studio = Studio.objects.create(name='Studio Almagro')
        studio.delete()
        url = reverse('studios-detail', args=[studio.pk])
        response = admin_client.get(url)
        assert response.status_code == 200
        assert response.data['deleted'] is not None

    def test_patch_deleted_null_restores(self, admin_client):
        studio = Studio.objects.create(name='Studio Flores')
        studio.delete()
        url = reverse('studios-detail', args=[studio.pk])
        response = admin_client.patch(url, {'deleted': None}, format='json')
        assert response.status_code == 200
        assert response.data['deleted'] is None
        studio.refresh_from_db()
        assert studio.deleted is None
        assert Studio.objects.filter(pk=studio.pk).exists()

    def test_consultor_cannot_restore_deleted(self, consultor_client):
        studio = Studio.objects.create(name='Studio Liniers')
        studio.delete()
        url = reverse('studios-detail', args=[studio.pk])
        response = consultor_client.patch(url, {'deleted': None}, format='json')
        assert response.status_code == 404
        studio.refresh_from_db()
        assert studio.deleted is not None


# Filtro común por estudio

from rest_framework.request import Request as _DRFRequest
from rest_framework.test import APIRequestFactory as _APIRequestFactory
from rest_framework.exceptions import NotFound as _NotFound
from apps.studios.filters import (
    InvalidStudioParam, parse_studio_ids, resolve_studios, deleted_studios_detail,
)


def _req(query=''):
    return _DRFRequest(_APIRequestFactory().get('/x/' + query))


class TestParseStudioIds:

    def test_sin_parametro_devuelve_none(self):
        assert parse_studio_ids(_req()) is None

    @pytest.mark.parametrize('query, expected', [
        ('?studio=3', [3]),
        ('?studio=1,2', [1, 2]),
        ('?studio=1&studio=2', [1, 2]),
        ('?studio=1,2&studio=3', [1, 2, 3]),
        ('?studio=2,2&studio=2', [2]),
        ('?studio=%201%20', [1]),
    ])
    def test_formatos_validos(self, query, expected):
        assert parse_studio_ids(_req(query)) == expected

    @pytest.mark.parametrize('query', [
        '?studio=', '?studio=abc', '?studio=-1', '?studio=0', '?studio=1.5',
        '?studio=1,', '?studio=1,abc', '?studio=1&studio=', '?studio=01',
    ])
    def test_formatos_invalidos_400(self, query):
        with pytest.raises(InvalidStudioParam) as exc:
            parse_studio_ids(_req(query))
        assert exc.value.status_code == 400
        assert str(exc.value.detail) == "El parámetro 'studio' debe ser un número entero positivo."


@pytest.mark.django_db
class TestResolveStudios:

    def test_inexistente_404_con_id(self):
        s = Studio.objects.create(name='A')
        with pytest.raises(_NotFound) as exc:
            resolve_studios(_req(f'?studio={s.pk},999999'))
        assert str(exc.value.detail) == 'No existe un estudio con id 999999.'

    def test_id_fuera_de_rango_es_404_no_500(self):
        with pytest.raises(_NotFound):
            resolve_studios(_req('?studio=99999999999999'))

    def test_estudio_dado_de_baja_existe(self):
        s = Studio.objects.create(name='Cerrado')
        s.delete()
        studios = resolve_studios(_req(f'?studio={s.pk}'))
        assert [x.pk for x in studios] == [s.pk]
        assert deleted_studios_detail(studios) == f'El estudio con id {s.pk} está dado de baja.'

    def test_detail_none_si_ninguno_esta_de_baja(self):
        s = Studio.objects.create(name='Abierto')
        assert deleted_studios_detail(resolve_studios(_req(f'?studio={s.pk}'))) is None

    def test_detail_varios_de_baja(self):
        a = Studio.objects.create(name='A')
        b = Studio.objects.create(name='B')
        a.delete(); b.delete()
        detail = deleted_studios_detail([a, b])
        assert detail == f'Los estudios con id {a.pk}, {b.pk} están dados de baja.'
