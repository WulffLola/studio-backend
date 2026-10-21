import io
import pytest
from datetime import date, time, timedelta
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from .models import Person, PersonActivePlan
from apps.slots.models import SlotTemplate, FixedSlot


def _make_image(name='photo.jpg', content_type='image/jpeg', size_kb=10):
    """Crea un archivo de imagen falso en memoria para tests."""
    content = b'\xff\xd8\xff\xe0' + b'\x00' * (size_kb * 1024)
    return SimpleUploadedFile(name, content, content_type=content_type)

@pytest.mark.django_db
class TestPersonSoftDelete:

    def test_delete_sets_deleted(self):
        person = Person.objects.create(name='Juan', last_name='Perez', dni='12345678')
        person.delete()
        person.refresh_from_db()
        assert person.deleted is not None

    def test_objects_hides_deleted(self):
        person = Person.objects.create(name='Juan', last_name='Perez', dni='12345678')
        person.delete()
        assert not Person.objects.filter(pk=person.pk).exists()

    def test_all_objects_includes_deleted(self):
        person = Person.objects.create(name='Juan', last_name='Perez', dni='12345678')
        person.delete()
        assert Person.all_objects.filter(pk=person.pk).exists()

    def test_all_objects_dead_returns_deleted(self):
        person = Person.objects.create(name='Juan', last_name='Perez', dni='12345678')
        person.delete()
        assert Person.all_objects.dead().filter(pk=person.pk).exists()

    def test_all_objects_alive_excludes_deleted(self):
        person = Person.objects.create(name='Juan', last_name='Perez', dni='12345678')
        person.delete()
        assert not Person.all_objects.alive().filter(pk=person.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user):
        person = Person.objects.create(name='Juan', last_name='Perez', dni='12345678')
        person.delete()
        qs = Person.all_objects.for_user(admin_user)
        assert qs.filter(pk=person.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user):
        person = Person.objects.create(name='Juan', last_name='Perez', dni='12345678')
        person.delete()
        qs = Person.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=person.pk).exists()

    def test_restore(self):
        person = Person.objects.create(name='Juan', last_name='Perez', dni='12345678')
        person.delete()
        person.restore()
        person.refresh_from_db()
        assert person.deleted is None

    def test_hard_delete_removes_from_db(self):
        person = Person.objects.create(name='Juan', last_name='Perez', dni='12345678')
        pk = person.pk
        person.hard_delete()
        assert not Person.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestPeopleViewForUser:
    URL = 'people-list'

    def test_admin_list_includes_deleted(self, admin_client):
        person = Person.objects.create(name='Juan', last_name='Perez', dni='12345678')
        person.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert person.id in ids

    def test_consultor_list_excludes_deleted(self, consultor_client):
        person = Person.objects.create(name='Juan', last_name='Perez', dni='12345678')
        person.delete()
        response = consultor_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert person.id not in ids

    def test_delete_endpoint_is_soft_delete(self, admin_client, monkeypatch):
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kwargs: None)
        person = Person.objects.create(name='Juan', last_name='Perez', dni='12345678')
        url = reverse('people-detail', args=[person.pk])
        response = admin_client.delete(url, data={'code': 'admin'}, format='json')
        assert response.status_code == 204
        assert Person.all_objects.filter(pk=person.pk).exists()
        person.refresh_from_db()
        assert person.deleted is not None

    def test_delete_endpoint_usa_timezone_now(self, admin_client, monkeypatch):
        # destroy() debe guardar deleted con timezone.now() (aware), no
        # datetime.now() (naive) que corre la fecha bajo USE_TZ=True. deuda)
        from datetime import datetime, timezone as dtz
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kwargs: None)
        fixed = datetime(2026, 3, 15, 13, 0, tzinfo=dtz.utc)
        monkeypatch.setattr('apps.people.views.timezone.now', lambda: fixed)
        person = Person.objects.create(name='Del', last_name='Baja', dni='90909090')
        url = reverse('people-detail', args=[person.pk])
        response = admin_client.delete(url, data={'code': 'admin'}, format='json')
        assert response.status_code == 204
        person.refresh_from_db()
        assert person.deleted == fixed

    def test_create_person_success(self, admin_client):
        url = reverse(self.URL)
        data = {
            'name': 'Test',
            'last_name': 'User',
            'dni': '11223344',
            'email': 'test@user.com',
            'phone': '12345678',
            'sex': 'M',
            'birth_date': '1990-01-01'
        }
        response = admin_client.post(url, data=data, format='json')
        assert response.status_code == 201
        assert Person.objects.filter(dni='11223344').exists()

    def test_create_person_missing_fields(self, admin_client):
        url = reverse(self.URL)
        data = {
            'name': 'Test',
            # missing last_name, dni, etc.
        }
        response = admin_client.post(url, data=data, format='json')
        assert response.status_code == 400
        assert 'error' in response.data
        assert 'last_name' in response.data['error']

    def test_create_person_duplicate_dni(self, admin_client):
        Person.objects.create(name='Juan', last_name='Perez', dni='12345678', email='j@p.com', phone='1', sex='M', birth_date='1990-01-01')
        url = reverse(self.URL)
        data = {
            'name': 'Test',
            'last_name': 'User',
            'dni': '12345678',
            'email': 'test@user.com',
            'phone': '12345678',
            'sex': 'M',
            'birth_date': '1990-01-01'
        }
        response = admin_client.post(url, data=data, format='json')
        assert response.status_code == 400
        assert 'error' in response.data

    def test_update_person_duplicate_dni(self, admin_client):
        Person.objects.create(name='Juan', last_name='Perez', dni='12345678', email='j@p.com', phone='1', sex='M', birth_date='1990-01-01')
        person2 = Person.objects.create(name='Ana', last_name='Gomez', dni='87654321', email='a@g.com', phone='2', sex='F', birth_date='1990-01-02')
        
        url = reverse('people-detail', args=[person2.pk])
        data = {
            'dni': '12345678'
        }
        response = admin_client.patch(url, data=data, format='json')
        assert response.status_code == 400
        assert "ya está registrada" in response.data['error']


@pytest.mark.django_db
class TestPersonProfilePhoto:
    UPLOAD_URL = 'people-upload-photo'

    def test_admin_can_upload_photo(self, admin_client):
        """El admin puede subir una foto de perfil para un alumno."""
        person = Person.objects.create(name='Ana', last_name='García', dni='11111111')
        url = reverse(self.UPLOAD_URL, args=[person.pk])
        response = admin_client.patch(url, data={'profile_photo': _make_image()}, format='multipart')
        assert response.status_code == 200
        assert 'profile_photo' in response.data
        person.refresh_from_db()
        assert person.profile_photo

    def test_upload_replaces_previous_photo(self, admin_client):
        """Subir una segunda foto reemplaza la anterior."""
        person = Person.objects.create(name='Ana', last_name='García', dni='11111111')
        url = reverse(self.UPLOAD_URL, args=[person.pk])
        admin_client.patch(url, data={'profile_photo': _make_image('first.jpg')}, format='multipart')
        admin_client.patch(url, data={'profile_photo': _make_image('second.jpg')}, format='multipart')
        person.refresh_from_db()
        assert 'second' in person.profile_photo.name

    def test_anonymous_cannot_upload(self):
        """Un usuario anónimo no puede subir fotos."""
        from rest_framework.test import APIClient
        person = Person.objects.create(name='Ana', last_name='García', dni='11111111')
        url = reverse(self.UPLOAD_URL, args=[person.pk])
        response = APIClient().patch(url, data={'profile_photo': _make_image()}, format='multipart')
        assert response.status_code in (401, 403)

    def test_file_too_large_returns_400(self, admin_client):
        """Archivos mayores a 5 MB son rechazados."""
        person = Person.objects.create(name='Ana', last_name='García', dni='11111111')
        url = reverse(self.UPLOAD_URL, args=[person.pk])
        big_file = _make_image(size_kb=6 * 1024)  # 6 MB
        response = admin_client.patch(url, data={'profile_photo': big_file}, format='multipart')
        assert response.status_code == 400

    def test_invalid_format_returns_400(self, admin_client):
        """Archivos que no son imagen (ej: PDF) son rechazados."""
        person = Person.objects.create(name='Ana', last_name='García', dni='11111111')
        url = reverse(self.UPLOAD_URL, args=[person.pk])
        pdf = SimpleUploadedFile('doc.pdf', b'%PDF-1.4', content_type='application/pdf')
        response = admin_client.patch(url, data={'profile_photo': pdf}, format='multipart')
        assert response.status_code == 400

    def test_person_with_no_photo_has_null_field(self):
        """Una persona sin foto tiene profile_photo null."""
        person = Person.objects.create(name='Ana', last_name='García', dni='11111111')
        assert not person.profile_photo


@pytest.mark.django_db
class TestPersonActivePlanModel:

    def test_is_active_with_valid_plan(self, person_active_plan):
        assert person_active_plan.is_active() is True

    def test_is_active_expired_by_date(self, person, plans_type):
        past = timezone.now().date() - timedelta(days=1)
        pap = PersonActivePlan.objects.create(
            person=person, plans_type=plans_type,
            exp_date=past, sessions_total=10, sessions_remaining=5,
        )
        assert pap.is_active() is False

    def test_is_active_no_sessions(self, person, plans_type):
        future = timezone.now().date() + timedelta(days=30)
        pap = PersonActivePlan.objects.create(
            person=person, plans_type=plans_type,
            exp_date=future, sessions_total=10, sessions_remaining=0,
        )
        assert pap.is_active() is False

    def test_deduct_session(self, person_active_plan):
        initial = person_active_plan.sessions_remaining
        assert person_active_plan.deduct_session() is True
        person_active_plan.refresh_from_db()
        assert person_active_plan.sessions_remaining == initial - 1

    def test_deduct_session_no_baja_de_cero(self, person_active_plan):
        # con 1 sesión, descuenta una sola vez; el segundo intento falla
        # y sessions_remaining nunca queda negativo (UPDATE condicional atómico).
        person_active_plan.sessions_remaining = 1
        person_active_plan.save(update_fields=['sessions_remaining'])
        assert person_active_plan.deduct_session() is True
        person_active_plan.refresh_from_db()
        assert person_active_plan.sessions_remaining == 0
        assert person_active_plan.deduct_session() is False
        person_active_plan.refresh_from_db()
        assert person_active_plan.sessions_remaining == 0  # nunca -1

    def test_restore_session_atomico_no_pisa_descuentos(self, person_active_plan):
        # restore usa UPDATE con F(), así no pisa un descuento concurrente
        # hecho sobre la DB mientras teníamos una instancia con valor viejo.
        person_active_plan.sessions_remaining = 2
        person_active_plan.save(update_fields=['sessions_remaining'])
        # Otra transacción descontó en la DB (la instancia en memoria sigue en 2).
        PersonActivePlan.objects.filter(pk=person_active_plan.pk).update(sessions_remaining=1)
        person_active_plan.restore_session()
        person_active_plan.refresh_from_db()
        assert person_active_plan.sessions_remaining == 2  # 1 + 1 (F), no 3

    def test_soft_delete(self, person_active_plan):
        person_active_plan.delete()
        person_active_plan.refresh_from_db()
        assert person_active_plan.deleted is not None

    def test_objects_hides_deleted(self, person_active_plan):
        person_active_plan.delete()
        assert not PersonActivePlan.objects.filter(pk=person_active_plan.pk).exists()

    def test_all_objects_includes_deleted(self, person_active_plan):
        person_active_plan.delete()
        assert PersonActivePlan.all_objects.filter(pk=person_active_plan.pk).exists()

    def test_restore(self, person_active_plan):
        person_active_plan.delete()
        person_active_plan.restore()
        person_active_plan.refresh_from_db()
        assert person_active_plan.deleted is None

    def test_hard_delete(self, person_active_plan):
        pk = person_active_plan.pk
        person_active_plan.hard_delete()
        assert not PersonActivePlan.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestPersonActivePlanView:
    URL = 'person-active-plan-list'

    def test_list_returns_ok(self, admin_client, person_active_plan):
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert person_active_plan.id in ids

    def test_filter_by_person(self, admin_client, person, person_active_plan):
        other = Person.objects.create(name='Ana', last_name='Lopez', dni='11112222')
        response = admin_client.get(reverse(self.URL), {'person': other.id})
        assert response.status_code == 200
        assert response.data == []

    def test_filter_by_person_returns_own(self, admin_client, person, person_active_plan):
        response = admin_client.get(reverse(self.URL), {'person': person.id})
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert person_active_plan.id in ids

    def test_create_person_active_plan(self, admin_client, person, plans_type):
        future = (timezone.now().date() + timedelta(days=30)).isoformat()
        response = admin_client.post(reverse(self.URL), data={
            'person': person.id,
            'plans_type_id': plans_type.id,
            'exp_date': future,
            'sessions_total': 8,
            'sessions_remaining': 8,
        }, format='json')
        assert response.status_code == 201
        assert PersonActivePlan.objects.filter(person=person, plans_type=plans_type).exists()

    def test_delete_is_soft_delete(self, admin_client, person_active_plan):
        url = reverse('person-active-plan-detail', args=[person_active_plan.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert PersonActivePlan.all_objects.filter(pk=person_active_plan.pk).exists()
        person_active_plan.refresh_from_db()
        assert person_active_plan.deleted is not None


class TestIdentitySyncViaAPI:
    @pytest.mark.django_db
    def test_person_update_via_api_propagates_to_user(self, admin_client, user_types):
        from datetime import date
        from django.urls import reverse
        from apps.users.models import CustomUser

        person = Person.objects.create(
            name='Ana', last_name='Lopez', dni='55556666', email='ana@test.com',
            phone='111', sex='F', birth_date=date(1990, 5, 5),
        )
        user = CustomUser.objects.create_user(
            email='ana@test.com', password='x', name='Ana', last_name='Lopez',
            dni='55556666', tipo_usuario=user_types['student'], person=person,
        )
        url = reverse('people-detail', args=[person.id])
        resp = admin_client.put(url, {
            'name': 'Ana Maria', 'last_name': 'Lopez', 'dni': '55556666',
            'email': 'ana@test.com', 'phone': '222', 'sex': 'F',
            'birth_date': '1990-05-05',
        }, format='json')
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.name == 'Ana Maria'
        assert user.phone == '222'

    @pytest.mark.django_db
    def test_user_update_via_api_propagates_to_person(self, super_client, user_types):
        from django.urls import reverse
        from apps.users.models import CustomUser

        person = Person.objects.create(
            name='Leo', last_name='Diaz', dni='66667777', email='leo@test.com', phone='1',
        )
        user = CustomUser.objects.create_user(
            email='leo@test.com', password='x', name='Leo', last_name='Diaz',
            dni='66667777', tipo_usuario=user_types['student'], person=person,
        )
        url = reverse('users-detail', args=[user.id])
        resp = super_client.put(url, {
            'name': 'Leonardo', 'phone': '999', 'tipo_usuario': user_types['student'].id,
        }, format='json')
        assert resp.status_code == 200
        person.refresh_from_db()
        assert person.name == 'Leonardo'
        assert person.phone == '999'


# Soft-delete cascade: Person -> FixedSlot
# Por qué: al eliminar suavemente una Person, sus turnos fijos activos deben
# quedar también eliminados suavemente, para evitar turnos fijos huérfanos.

@pytest.mark.django_db
class TestPersonFixedSlotCascade:
    """Soft-delete de Person propaga el soft-delete a sus FixedSlot activos."""

    def _make_template(self, week, room):
        t = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0), room=room, availability=10,
        )
        t.days_of_week.set([week])
        return t

    def test_soft_delete_cascades_a_fixed_slots(self, person, week, room):
        """Soft-delete de Person setea deleted en sus FixedSlot activos."""
        t = self._make_template(week, room)
        fs = FixedSlot.objects.create(person=person, template=t, start_date=date.today())
        person.delete()
        fs.refresh_from_db()
        assert fs.deleted is not None

    def test_fixed_slots_ocultos_tras_soft_delete_persona(self, person, week, room):
        """Tras soft-delete de Person, sus FixedSlot desaparecen de FixedSlot.objects."""
        t = self._make_template(week, room)
        fs = FixedSlot.objects.create(person=person, template=t, start_date=date.today())
        person.delete()
        assert not FixedSlot.objects.filter(pk=fs.pk).exists()

    def test_no_afecta_fixed_slots_de_otra_persona(self, week, room):
        """Soft-delete de una Person no afecta los FixedSlot de otra Person."""
        persona_a = Person.objects.create(name='Ana', last_name='Lopez', dni='11111111')
        persona_b = Person.objects.create(name='Bob', last_name='Smith', dni='22222222')
        t_a = self._make_template(week, room)
        t_b = SlotTemplate.objects.create(
            start_time=time(11, 0), end_time=time(12, 0), room=room, availability=10,
        )
        t_b.days_of_week.set([week])
        FixedSlot.objects.create(person=persona_a, template=t_a, start_date=date.today())
        fs_b = FixedSlot.objects.create(person=persona_b, template=t_b, start_date=date.today())
        persona_a.delete()
        assert FixedSlot.objects.filter(pk=fs_b.pk).exists()
        fs_b.refresh_from_db()
        assert fs_b.deleted is None

    def test_no_re_borra_fixed_slot_ya_eliminado(self, person, week, room):
        """Un FixedSlot ya soft-deleted mantiene su fecha deleted original tras el cascade."""
        t = self._make_template(week, room)
        fs = FixedSlot.objects.create(person=person, template=t, start_date=date.today())
        original_deleted = date(2026, 1, 1)
        FixedSlot.all_objects.filter(pk=fs.pk).update(deleted=original_deleted)
        person.delete()
        fs.refresh_from_db()
        assert fs.deleted == original_deleted


@pytest.mark.django_db
class TestPersonNoLegacyPlan:
    """ /people/ ya no expone el Plan legacy."""
    URL = 'people-list'

    def test_person_response_has_no_plan(self, admin_client, person):
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        for row in resp.data:
            assert 'plan' not in row


# /people/ expone los planes activos del alumno, comentario Agostina)

@pytest.mark.django_db
class TestPersonActivePlansEmbedded:
    """ /people/ expone active_plans (con plans_subtype) en vez del viejo campo plan."""
    URL = 'people-list'

    def _row_for(self, resp, person_id):
        return next(r for r in resp.data if r['id'] == person_id)

    def test_incluye_active_plans_con_plans_subtype(self, admin_client, person, plans_subtype_a, plans_subtype_b):
        PersonActivePlan.objects.create(
            person=person, plans_subtype=plans_subtype_a,
            exp_date=date.today() + timedelta(days=30), sessions_total=8, sessions_remaining=8,
        )
        PersonActivePlan.objects.create(
            person=person, plans_subtype=plans_subtype_b,
            exp_date=date.today() + timedelta(days=30), sessions_total=8, sessions_remaining=8,
        )
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        row = self._row_for(resp, person.id)
        assert 'active_plans' in row
        assert len(row['active_plans']) == 2
        subtype_ids = {ap['plans_subtype']['id'] for ap in row['active_plans']}
        assert subtype_ids == {plans_subtype_a.id, plans_subtype_b.id}

    def test_sin_planes_lista_vacia(self, admin_client, person):
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        row = self._row_for(resp, person.id)
        assert row['active_plans'] == []

    def test_plan_soft_deleted_no_aparece(self, admin_client, person, plans_subtype_a):
        ap = PersonActivePlan.objects.create(
            person=person, plans_subtype=plans_subtype_a,
            exp_date=date.today() + timedelta(days=30), sessions_total=8, sessions_remaining=8,
        )
        ap.deleted = date.today()
        ap.save()
        resp = admin_client.get(reverse(self.URL))
        row = self._row_for(resp, person.id)
        assert row['active_plans'] == []

    def test_crear_person_sigue_funcionando(self, admin_client):
        payload = {
            'name': 'Nueva', 'last_name': 'Persona', 'dni': '55000001',
            'email': 'nueva@example.com', 'phone': '1122334455',
            'sex': 'Femenino', 'birth_date': '1990-01-01',
        }
        resp = admin_client.post(reverse(self.URL), data=payload, format='json')
        assert resp.status_code == 201, resp.data


@pytest.mark.django_db
class TestRestoreSession:
    def test_restore_session_incrementa_uno(self, person_active_plan):
        antes = person_active_plan.sessions_remaining
        person_active_plan.restore_session()
        person_active_plan.refresh_from_db()
        assert person_active_plan.sessions_remaining == antes + 1


@pytest.mark.django_db
class TestFindConsumablePlan:
    def _plan(self, person, plans_subtype_a, exp_days, sessions):
        from datetime import timedelta
        from django.utils import timezone
        from apps.people.models import PersonActivePlan
        return PersonActivePlan.objects.create(
            person=person, plans_subtype=plans_subtype_a,
            exp_date=timezone.now().date() + timedelta(days=exp_days),
            sessions_total=sessions, sessions_remaining=sessions,
        )

    def test_matchea_por_actividad_vigente_con_sesiones(self, person, slot_with_activity, plans_subtype_a):
        from apps.people.selectors import find_consumable_plan
        p = self._plan(person, plans_subtype_a, 30, 5)
        assert find_consumable_plan(person, slot_with_activity).id == p.id

    def test_none_si_slot_sin_actividad(self, person, slot, plans_subtype_a):
        from apps.people.selectors import find_consumable_plan
        self._plan(person, plans_subtype_a, 30, 5)
        assert find_consumable_plan(person, slot) is None

    def test_none_si_sin_sesiones(self, person, slot_with_activity, plans_subtype_a):
        from apps.people.selectors import find_consumable_plan
        self._plan(person, plans_subtype_a, 30, 0)
        assert find_consumable_plan(person, slot_with_activity) is None

    def test_elige_el_que_vence_antes(self, person, slot_with_activity, plans_subtype_a):
        from apps.people.selectors import find_consumable_plan
        lejano = self._plan(person, plans_subtype_a, 60, 5)
        cercano = self._plan(person, plans_subtype_a, 10, 5)
        assert find_consumable_plan(person, slot_with_activity).id == cercano.id

    def test_has_plan_for_activity_true_aunque_sin_sesiones(self, person, slot_with_activity, plans_subtype_a):
        from apps.people.selectors import person_has_plan_for_activity
        self._plan(person, plans_subtype_a, 30, 0)
        assert person_has_plan_for_activity(person, slot_with_activity) is True


@pytest.mark.django_db
class TestDeletedPeopleDateFilterKAN149:
    """ /deleted-people/ filtra por fecha de baja (deleted) con date_from
    y date_to (obligatorios, YYYY-MM-DD, rango validado)."""
    URL = 'deleted-people-list'

    def _delete_on(self, name, dni, when):
        from datetime import datetime
        p = Person.objects.create(name=name, last_name='X', dni=dni)
        Person.all_objects.filter(pk=p.pk).update(
            deleted=timezone.make_aware(datetime(*when, 12, 0))
        )
        return p

    def _dnis(self, data):
        return [p['dni'] for day in data.values() for p in day]

    def test_faltan_ambos_devuelve_400(self, admin_client):
        assert admin_client.get(reverse(self.URL)).status_code == 400

    def test_falta_date_to_devuelve_400(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'date_from': '2026-01-01'})
        assert resp.status_code == 400

    def test_falta_date_from_devuelve_400(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'date_to': '2026-01-31'})
        assert resp.status_code == 400

    def test_formato_invalido_devuelve_400(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'date_from': '01-01-2026', 'date_to': '2026-01-31'})
        assert resp.status_code == 400

    def test_from_mayor_que_to_devuelve_400(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'date_from': '2026-02-01', 'date_to': '2026-01-01'})
        assert resp.status_code == 400

    def test_filtra_por_rango_de_baja(self, admin_client):
        self._delete_on('Ana', '111', (2026, 1, 10))
        self._delete_on('Beto', '222', (2026, 1, 20))
        self._delete_on('Caro', '333', (2026, 2, 5))  # fuera del rango
        resp = admin_client.get(reverse(self.URL), {'date_from': '2026-01-01', 'date_to': '2026-01-31'})
        assert resp.status_code == 200
        dnis = self._dnis(resp.data)
        assert set(dnis) == {'111', '222'}
        assert '333' not in dnis

    def test_bordes_inclusivos(self, admin_client):
        self._delete_on('Edge1', '444', (2026, 1, 1))
        self._delete_on('Edge2', '555', (2026, 1, 31))
        resp = admin_client.get(reverse(self.URL), {'date_from': '2026-01-01', 'date_to': '2026-01-31'})
        assert set(self._dnis(resp.data)) == {'444', '555'}

    def test_agrupa_por_dia_local_no_utc(self, admin_client):
        # Baja a las 23:00 hora local (Buenos Aires, UTC-3). En UTC es el día
        # siguiente; debe agruparse y filtrarse por el día LOCAL.
        from datetime import datetime
        p = Person.objects.create(name='Noche', last_name='X', dni='666')
        Person.all_objects.filter(pk=p.pk).update(
            deleted=timezone.make_aware(datetime(2026, 1, 10, 23, 0))
        )
        resp = admin_client.get(reverse(self.URL), {'date_from': '2026-01-10', 'date_to': '2026-01-10'})
        assert resp.status_code == 200
        assert '2026-01-10' in resp.data
        assert self._dnis(resp.data) == ['666']

    def test_rango_sin_resultados_devuelve_200_vacio(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'date_from': '2020-01-01', 'date_to': '2020-01-31'})
        assert resp.status_code == 200
        assert resp.data == {}

    def test_rango_mayor_a_366_dias_devuelve_400(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'date_from': '2024-01-01', 'date_to': '2026-01-01'})
        assert resp.status_code == 400

    def test_rango_de_366_dias_es_valido(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'date_from': '2025-01-01', 'date_to': '2026-01-02'})
        assert resp.status_code == 200
