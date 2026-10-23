import pytest
from django.urls import reverse
from .models import TeachersTurn


@pytest.mark.django_db
class TestTeachersTurnSoftDelete:

    def test_delete_sets_deleted(self, teacher, slot):
        turn = TeachersTurn.objects.create(teacher=teacher, slot=slot, rol='Instructor')
        turn.delete()
        turn.refresh_from_db()
        assert turn.deleted is not None

    def test_objects_hides_deleted(self, teacher, slot):
        turn = TeachersTurn.objects.create(teacher=teacher, slot=slot, rol='Instructor')
        turn.delete()
        assert not TeachersTurn.objects.filter(pk=turn.pk).exists()

    def test_all_objects_includes_deleted(self, teacher, slot):
        turn = TeachersTurn.objects.create(teacher=teacher, slot=slot, rol='Instructor')
        turn.delete()
        assert TeachersTurn.all_objects.filter(pk=turn.pk).exists()

    def test_all_objects_dead_returns_deleted(self, teacher, slot):
        turn = TeachersTurn.objects.create(teacher=teacher, slot=slot, rol='Instructor')
        turn.delete()
        assert TeachersTurn.all_objects.dead().filter(pk=turn.pk).exists()

    def test_all_objects_alive_excludes_deleted(self, teacher, slot):
        turn = TeachersTurn.objects.create(teacher=teacher, slot=slot, rol='Instructor')
        turn.delete()
        assert not TeachersTurn.all_objects.alive().filter(pk=turn.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user, teacher, slot):
        turn = TeachersTurn.objects.create(teacher=teacher, slot=slot, rol='Instructor')
        turn.delete()
        qs = TeachersTurn.all_objects.for_user(admin_user)
        assert qs.filter(pk=turn.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user, teacher, slot):
        turn = TeachersTurn.objects.create(teacher=teacher, slot=slot, rol='Instructor')
        turn.delete()
        qs = TeachersTurn.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=turn.pk).exists()

    def test_restore(self, teacher, slot):
        turn = TeachersTurn.objects.create(teacher=teacher, slot=slot, rol='Instructor')
        turn.delete()
        turn.restore()
        turn.refresh_from_db()
        assert turn.deleted is None

    def test_hard_delete_removes_from_db(self, teacher, slot):
        turn = TeachersTurn.objects.create(teacher=teacher, slot=slot, rol='Instructor')
        pk = turn.pk
        turn.hard_delete()
        assert not TeachersTurn.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestTeachersTurnViewForUser:
    URL = 'teachers-turn-list'

    def test_admin_list_includes_deleted(self, admin_client, teacher, slot):
        turn = TeachersTurn.objects.create(teacher=teacher, slot=slot, rol='Instructor')
        turn.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert turn.id in ids

    def test_consultor_cannot_access(self, consultor_client):
        response = consultor_client.get(reverse(self.URL))
        assert response.status_code == 403

    def test_delete_endpoint_is_soft_delete(self, admin_client, teacher, slot):
        turn = TeachersTurn.objects.create(teacher=teacher, slot=slot, rol='Instructor')
        url = reverse('teachers-turn-detail', args=[turn.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert TeachersTurn.all_objects.filter(pk=turn.pk).exists()
        turn.refresh_from_db()
        assert turn.deleted is not None


# filtro opcional por estudio en /teachers-turn/

MSG_400 = "El parámetro 'studio' debe ser un número entero positivo."


@pytest.mark.django_db
class TestTeachersTurnStudioFilterKAN145:
    URL = 'teachers-turn-list'

    @pytest.fixture
    def data(self, teacher, slot, slot_b):
        # slot está en una sala de `studio`, slot_b en una sala de `studio_b`
        a1 = TeachersTurn.objects.create(teacher=teacher, slot=slot, rol='Instructor')
        a2 = TeachersTurn.objects.create(teacher=teacher, slot=slot, rol='Recepcion')
        b1 = TeachersTurn.objects.create(teacher=teacher, slot=slot_b, rol='Instructor')
        return {'a': {a1.id, a2.id}, 'b': {b1.id}}

    def _ids(self, response):
        return {t['id'] for t in response.data}

    def test_sin_filtro_devuelve_todos(self, admin_client, data):
        r = admin_client.get(reverse(self.URL))
        assert r.status_code == 200
        assert self._ids(r) == data['a'] | data['b']

    def test_filtra_estudio_a(self, admin_client, data, studio):
        r = admin_client.get(reverse(self.URL), {'studio': studio.id})
        assert r.status_code == 200
        assert self._ids(r) == data['a']

    def test_filtra_estudio_b(self, admin_client, data, studio_b):
        r = admin_client.get(reverse(self.URL), {'studio': studio_b.id})
        assert r.status_code == 200
        assert self._ids(r) == data['b']

    def test_varios_estudios(self, admin_client, data, studio, studio_b):
        r = admin_client.get(reverse(self.URL) + f'?studio={studio.id},{studio_b.id}')
        assert r.status_code == 200
        assert self._ids(r) == data['a'] | data['b']

    @pytest.mark.parametrize('value', ['abc', '-1', ''])
    def test_studio_invalido_400(self, admin_client, data, value):
        r = admin_client.get(reverse(self.URL) + f'?studio={value}')
        assert r.status_code == 400
        assert r.data == {'detail': MSG_400}

    def test_studio_inexistente_404(self, admin_client, data):
        r = admin_client.get(reverse(self.URL), {'studio': 999999})
        assert r.status_code == 404
        assert r.data == {'detail': 'No existe un estudio con id 999999.'}

    def test_usuario_sin_permiso_403(self, no_role_client, data, studio):
        r = no_role_client.get(reverse(self.URL), {'studio': studio.id})
        assert r.status_code == 403

    def test_consultor_sigue_sin_acceso_403(self, consultor_client, data, studio):
        # El endpoint ya era solo Admin/Super; el filtro no cambia eso.
        r = consultor_client.get(reverse(self.URL), {'studio': studio.id})
        assert r.status_code == 403

    def test_usuario_con_permiso_200(self, super_client, data, studio):
        r = super_client.get(reverse(self.URL), {'studio': studio.id})
        assert r.status_code == 200
        assert self._ids(r) == data['a']

    def test_estudio_sin_datos_200_vacio(self, admin_client, data, empty_studio):
        r = admin_client.get(reverse(self.URL), {'studio': empty_studio.id})
        assert r.status_code == 200
        assert r.data == []

    def test_estudio_dado_de_baja_envuelve_respuesta(self, admin_client, teacher, status, deleted_studio):
        from datetime import date, time
        from apps.rooms.models import Room
        from apps.slots.models import Slot
        room = Room.all_objects.create(name='Sala vieja', studio=deleted_studio)
        sl = Slot.objects.create(status=status, room=room, date=date.today(),
                                 start_time=time(8, 0), end_time=time(9, 0), availability=5)
        t = TeachersTurn.objects.create(teacher=teacher, slot=sl, rol='Instructor')
        r = admin_client.get(reverse(self.URL), {'studio': deleted_studio.id})
        assert r.status_code == 200
        assert r.data['detail'] == f'El estudio con id {deleted_studio.id} está dado de baja.'
        assert [x['id'] for x in r.data['results']] == [t.id]
