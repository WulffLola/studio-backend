import pytest
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse
from rest_framework.test import APIClient
from apps.people.models import Person
from .models import SwornStatement, PersonSwornStatement, AppointmentSwornStatement


# Fixtures locales

@pytest.fixture
def statement(db):
    return SwornStatement.objects.create(text='Declaro bajo juramento que estoy en buenas condiciones.')


@pytest.fixture
def person(db):
    return Person.objects.create(name='Ana', last_name='García', dni='11111111')


# Tests de SwornStatement (texto)

@pytest.mark.django_db
class TestSwornStatementViewSet:
    LIST_URL = 'sworn-statement-list'
    DETAIL_URL = 'sworn-statement-detail'

    def test_anonymous_can_list(self, statement):
        """Cualquier persona puede leer el texto de la declaración (necesario para el registro público)."""
        client = APIClient()
        response = client.get(reverse(self.LIST_URL))
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]['text'] == statement.text

    def test_anonymous_cannot_create(self, db):
        """Solo el admin puede cargar/modificar el texto."""
        client = APIClient()
        response = client.post(
            reverse(self.LIST_URL),
            data={'text': 'Texto nuevo'},
            format='json',
        )
        assert response.status_code in (401, 403)

    def test_admin_can_create(self, admin_client, db):
        """El admin puede crear una nueva versión del texto."""
        response = admin_client.post(
            reverse(self.LIST_URL),
            data={'text': 'Texto de la declaración v1'},
            format='json',
        )
        assert response.status_code == 201
        assert SwornStatement.objects.count() == 1

    def test_admin_can_update(self, admin_client, statement):
        """El admin puede actualizar el texto de una declaración existente."""
        response = admin_client.patch(
            reverse(self.DETAIL_URL, args=[statement.id]),
            data={'text': 'Texto actualizado'},
            format='json',
        )
        assert response.status_code == 200
        statement.refresh_from_db()
        assert statement.text == 'Texto actualizado'

    def test_admin_can_soft_delete(self, admin_client, statement):
        """Eliminar hace soft delete, no borra de la DB."""
        response = admin_client.delete(reverse(self.DETAIL_URL, args=[statement.id]))
        assert response.status_code == 204
        # Soft delete: deleted no es null pero el objeto existe
        statement.refresh_from_db()
        assert statement.deleted is not None

    def test_deleted_statement_not_in_list(self, admin_client, statement):
        """Una declaración eliminada no aparece en el listado."""
        statement.delete()
        response = admin_client.get(reverse(self.LIST_URL))
        assert response.status_code == 200
        assert len(response.data) == 0

    def test_response_includes_created_at(self, statement):
        """La respuesta incluye la fecha de creación para saber qué versión es."""
        client = APIClient()
        response = client.get(reverse(self.LIST_URL))
        assert 'created_at' in response.data[0]

    def test_constraint_bloquea_dos_activas_del_mismo_tipo(self, db):
        """No puede haber dos declaraciones activas y no-borradas del mismo tipo."""
        SwornStatement.objects.create(text='A', statement_type='person', is_active=True)
        with pytest.raises(IntegrityError):
            SwornStatement.objects.create(text='B', statement_type='person', is_active=True)


@pytest.mark.django_db
class TestSwornStatementActivaUnica:
    LIST_URL = 'sworn-statement-list'

    def test_crear_segunda_general_desactiva_la_primera(self, admin_client):
        r1 = admin_client.post(reverse(self.LIST_URL),
                               {'text': 'General 1', 'statement_type': 'person'}, format='json')
        assert r1.status_code == 201
        r2 = admin_client.post(reverse(self.LIST_URL),
                               {'text': 'General 2', 'statement_type': 'person'}, format='json')
        assert r2.status_code == 201
        assert SwornStatement.objects.get(pk=r1.data['id']).is_active is False
        assert SwornStatement.objects.get(pk=r2.data['id']).is_active is True
        assert SwornStatement.objects.filter(statement_type='person', is_active=True).count() == 1

    def test_general_y_clase_activas_coexisten(self, admin_client):
        admin_client.post(reverse(self.LIST_URL),
                          {'text': 'G', 'statement_type': 'person'}, format='json')
        admin_client.post(reverse(self.LIST_URL),
                          {'text': 'C', 'statement_type': 'appointment'}, format='json')
        assert SwornStatement.objects.filter(is_active=True).count() == 2

    def test_alta_inactiva_no_desactiva_la_vigente(self, admin_client):
        r1 = admin_client.post(reverse(self.LIST_URL),
                               {'text': 'G1', 'statement_type': 'person'}, format='json')
        r2 = admin_client.post(reverse(self.LIST_URL),
                               {'text': 'G2', 'statement_type': 'person', 'is_active': False}, format='json')
        assert r2.status_code == 201
        assert SwornStatement.objects.get(pk=r1.data['id']).is_active is True

    def test_patch_reactivar_desactiva_la_otra_vigente(self, admin_client):
        r1 = admin_client.post(reverse(self.LIST_URL),
                               {'text': 'G1', 'statement_type': 'person'}, format='json')
        r2 = admin_client.post(reverse(self.LIST_URL),
                               {'text': 'G2', 'statement_type': 'person', 'is_active': False}, format='json')
        # reactivar la G2 debe desactivar la G1 (no 500)
        from django.urls import reverse as rev
        resp = admin_client.patch(rev('sworn-statement-detail', args=[r2.data['id']]),
                                  {'is_active': True}, format='json')
        assert resp.status_code == 200
        assert SwornStatement.objects.get(pk=r1.data['id']).is_active is False
        assert SwornStatement.objects.filter(statement_type='person', is_active=True).count() == 1


# Tests de la data-migration (0004_swornstatement_is_active)

@pytest.mark.django_db(transaction=True)
def test_data_migration_deja_una_activa_por_tipo():
    """
    La migración 0004 agrega is_active y, para datos preexistentes, debe dejar
    a lo sumo una fila activa (la más reciente) por statement_type.
    """
    app = 'sworn_statement'
    migrate_from = [(app, '0003_swornstatement_statement_type')]
    migrate_to = [(app, '0004_swornstatement_is_active')]

    executor = MigrationExecutor(connection)
    try:
        # Retroceder a 0003 (antes de is_active) y crear datos "viejos".
        executor.migrate(migrate_from)
        executor.loader.build_graph()
        OldSwornStatement = executor.loader.project_state(migrate_from).apps.get_model(
            app, 'SwornStatement'
        )
        for i in range(3):
            OldSwornStatement.objects.create(text=f'P{i}', statement_type='person')
        for i in range(2):
            OldSwornStatement.objects.create(text=f'A{i}', statement_type='appointment')

        # Aplicar 0004 (AddField + data-fix + AddConstraint).
        executor = MigrationExecutor(connection)
        executor.migrate(migrate_to)
        executor.loader.build_graph()
        NewSwornStatement = executor.loader.project_state(migrate_to).apps.get_model(
            app, 'SwornStatement'
        )

        assert NewSwornStatement.objects.filter(
            statement_type='person', is_active=True, deleted__isnull=True
        ).count() == 1
        assert NewSwornStatement.objects.filter(
            statement_type='appointment', is_active=True, deleted__isnull=True
        ).count() == 1
    finally:
        # Dejar la DB migrada al head para no romper otros tests.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db
def test_flags_existen_con_default_false():
    from apps.appointments.models import Appointment
    p = Person.objects.create(name='X', last_name='Y', dni='90000001')
    assert p.firmo_declaracion_general is False
    a = Appointment.objects.create(person=p)
    assert a.firmo_declaracion_clase is False


# Tests de PersonSwornStatement (firmas)

@pytest.mark.django_db
class TestPersonSwornStatementViewSet:
    LIST_URL = 'person-sworn-statement-list'

    def test_anonymous_cannot_sign(self, statement, person, db):
        """Firmar requiere estar autenticado: ya no es un flujo público."""
        client = APIClient()
        response = client.post(
            reverse(self.LIST_URL),
            data={'person': person.id, 'statement': statement.id},
            format='json',
        )
        assert response.status_code in (401, 403)
        assert PersonSwornStatement.objects.count() == 0

    def test_sign_records_signed_at(self, admin_client, admin_user, statement, person):
        """La firma guarda automáticamente la fecha/hora de aceptación."""
        admin_user.person = person
        admin_user.save()
        admin_client.post(
            reverse(self.LIST_URL),
            data={'user_id': admin_user.id, 'statement': statement.id},
            format='json',
        )
        sig = PersonSwornStatement.objects.first()
        assert sig is not None
        assert sig.signed_at is not None

    def test_anonymous_cannot_list(self, statement, person, db):
        """El listado de firmas es solo para admins."""
        client = APIClient()
        response = client.get(reverse(self.LIST_URL))
        assert response.status_code in (401, 403)

    def test_admin_can_list_signatures(self, admin_client, statement, person):
        """El admin puede ver quién firmó y cuándo."""
        PersonSwornStatement.objects.create(person=person, statement=statement)
        response = admin_client.get(reverse(self.LIST_URL))
        assert response.status_code == 200
        assert len(response.data) == 1

    def test_list_includes_person_name_and_statement_text(self, admin_client, statement, person):
        """El listado expone nombre del alumno y texto firmado para que el admin no tenga que cruzar tablas."""
        PersonSwornStatement.objects.create(person=person, statement=statement)
        response = admin_client.get(reverse(self.LIST_URL))
        item = response.data[0]
        assert 'person_name' in item
        assert 'statement_text' in item
        assert item['statement_text'] == statement.text

    def test_cannot_sign_nonexistent_statement(self, student_client, student_user, person):
        """Firmar una declaración que no existe devuelve 400."""
        student_user.person = person
        student_user.save()
        response = student_client.post(
            reverse(self.LIST_URL),
            data={'person': person.id, 'statement': 9999},
            format='json',
        )
        assert response.status_code == 400

    def test_cannot_patch_or_delete_signature(self, admin_client, statement, person):
        """Las firmas son inmutables: no se pueden editar ni borrar (solo POST y GET)."""
        sig = PersonSwornStatement.objects.create(person=person, statement=statement)
        url = reverse('person-sworn-statement-list') + f'{sig.id}/'
        patch_response = admin_client.patch(url, data={'person': person.id}, format='json')
        delete_response = admin_client.delete(url)
        assert patch_response.status_code == 405
        assert delete_response.status_code == 405


# Tests de sincronización de flags firmo_declaracion_*

@pytest.mark.django_db
class TestFlagsFirmaDeclaracion:
    def _general_activa(self):
        return SwornStatement.objects.create(text='G', statement_type='person', is_active=True)

    def _clase_activa(self):
        return SwornStatement.objects.create(text='C', statement_type='appointment', is_active=True)

    def test_firmar_general_activa_marca_person(self, db):
        from apps.sworn_statement.serializer import PersonSwornStatementSerializer
        p = Person.objects.create(name='A', last_name='B', dni='90000010')
        st = self._general_activa()
        ser = PersonSwornStatementSerializer(data={'person': p.id, 'statement': st.id})
        ser.is_valid(raise_exception=True); ser.save()
        p.refresh_from_db()
        assert p.firmo_declaracion_general is True

    def test_firmar_general_inactiva_no_marca(self, db):
        from apps.sworn_statement.serializer import PersonSwornStatementSerializer
        p = Person.objects.create(name='A', last_name='B', dni='90000011')
        st = SwornStatement.objects.create(text='vieja', statement_type='person', is_active=False)
        ser = PersonSwornStatementSerializer(data={'person': p.id, 'statement': st.id})
        ser.is_valid(raise_exception=True); ser.save()
        p.refresh_from_db()
        assert p.firmo_declaracion_general is False

    def test_firmar_clase_activa_marca_appointment(self, db):
        from apps.appointments.models import Appointment
        from apps.sworn_statement.serializer import AppointmentSwornStatementSerializer
        p = Person.objects.create(name='A', last_name='B', dni='90000012')
        a = Appointment.objects.create(person=p)
        st = self._clase_activa()
        ser = AppointmentSwornStatementSerializer(data={'appointment': a.id, 'statement': st.id})
        ser.is_valid(raise_exception=True); ser.save()
        a.refresh_from_db()
        assert a.firmo_declaracion_clase is True

    def test_publicar_nueva_general_resetea_person_no_appointment(self, db):
        from apps.appointments.models import Appointment
        from apps.sworn_statement.serializer import SwornStatementSerializer
        p = Person.objects.create(name='A', last_name='B', dni='90000013', firmo_declaracion_general=True)
        a = Appointment.objects.create(person=p, firmo_declaracion_clase=True)
        # publicar nueva general activa
        ser = SwornStatementSerializer(data={'text': 'nueva', 'statement_type': 'person'})
        ser.is_valid(raise_exception=True); ser.save()
        p.refresh_from_db(); a.refresh_from_db()
        assert p.firmo_declaracion_general is False   # reseteado
        assert a.firmo_declaracion_clase is True       # NO tocado

    def test_editar_text_de_general_activa_no_resetea_flags(self, db):
        from apps.sworn_statement.serializer import SwornStatementSerializer
        st = SwornStatement.objects.create(text='vigente', statement_type='person', is_active=True)
        p = Person.objects.create(name='A', last_name='B', dni='90000030', firmo_declaracion_general=True)
        # PATCH que solo cambia el text de la general YA activa
        ser = SwornStatementSerializer(st, data={'text': 'vigente corregido'}, partial=True)
        ser.is_valid(raise_exception=True); ser.save()
        p.refresh_from_db()
        assert p.firmo_declaracion_general is True   # NO se reseteó

    def test_reactivar_general_inactiva_si_resetea_flags(self, db):
        from apps.sworn_statement.serializer import SwornStatementSerializer
        vieja = SwornStatement.objects.create(text='vieja', statement_type='person', is_active=False)
        p = Person.objects.create(name='A', last_name='B', dni='90000031', firmo_declaracion_general=True)
        ser = SwornStatementSerializer(vieja, data={'is_active': True}, partial=True)
        ser.is_valid(raise_exception=True); ser.save()
        p.refresh_from_db()
        assert p.firmo_declaracion_general is False   # transición a activa => reset


# Tests de exposición read-only de los flags en la API

@pytest.mark.django_db
def test_person_serializer_expone_flag_readonly():
    from apps.people.serializer import PersonSerializer
    p = Person.objects.create(name='A', last_name='B', dni='90000020', firmo_declaracion_general=True)
    data = PersonSerializer(p).data
    assert data['firmo_declaracion_general'] is True
    # read-only: no se puede setear por input
    ser = PersonSerializer(p, data={'firmo_declaracion_general': False}, partial=True)
    ser.is_valid(raise_exception=True); ser.save()
    p.refresh_from_db()
    assert p.firmo_declaracion_general is True  # no cambió


@pytest.mark.django_db
def test_appointment_serializer_expone_flag_readonly():
    from apps.appointments.models import Appointment
    from apps.appointments.serializer import AppointmentSerializer
    p = Person.objects.create(name='A', last_name='B', dni='90000021')
    a = Appointment.objects.create(person=p, firmo_declaracion_clase=True)
    data = AppointmentSerializer(a).data
    assert data['firmo_declaracion_clase'] is True
    # read-only: no se puede setear por input
    ser = AppointmentSerializer(a, data={'firmo_declaracion_clase': False}, partial=True)
    ser.is_valid(raise_exception=True); ser.save()
    a.refresh_from_db()
    assert a.firmo_declaracion_clase is True  # read-only: no cambió


# Tests de seguridad: create() exige auth y no permite suplantar

@pytest.mark.django_db
class TestPersonSwornStatementSecurity:
    URL = 'person-sworn-statement-list'

    def _statement(self):
        return SwornStatement.objects.create(text='Declaración de prueba')

    def test_anonymous_create_is_rejected(self, person):
        st = self._statement()
        client = APIClient()
        response = client.post(
            reverse(self.URL),
            data={'user_id': 1, 'statement': st.id},
            format='json',
        )
        assert response.status_code in (401, 403)

    def test_student_signs_own(self, student_client, student_user, person):
        student_user.person = person
        student_user.save()
        st = self._statement()
        response = student_client.post(
            reverse(self.URL),
            data={'user_id': student_user.id, 'statement': st.id},
            format='json',
        )
        assert response.status_code == 201, response.data
        assert PersonSwornStatement.objects.filter(person=person).exists()

    def test_student_cannot_sign_for_other(self, student_client, student_user, admin_user, person):
        """El student intenta firmar por admin_user (otra person): se ignora el user_id
        ajeno y la firma se registra sobre el propio student, nunca sobre 'other'."""
        other = Person.objects.create(name='Otro', last_name='Alumno', dni='60000000')
        admin_user.person = other
        admin_user.save()
        student_user.person = person
        student_user.save()
        st = self._statement()
        response = student_client.post(
            reverse(self.URL),
            data={'user_id': admin_user.id, 'statement': st.id},
            format='json',
        )
        assert response.status_code == 201, response.data
        assert not PersonSwornStatement.objects.filter(person=other).exists()
        assert PersonSwornStatement.objects.filter(person=person).exists()

    def test_user_without_tipo_usuario_cannot_sign_for_other(self, person, admin_user):
        """Un usuario autenticado con tipo_usuario=None no debe ser tratado como admin
        (vector teórico si el chequeo de rol comparara PKs en vez de reusar las
        permission classes): no puede firmar por otro, solo por sí mismo."""
        from apps.users.models import CustomUser
        other = Person.objects.create(name='Sin', last_name='Tipo', dni='62000000')
        admin_user.person = other
        admin_user.save()
        no_type_user = CustomUser.objects.create_user(
            email='notype@test.com', password='x', name='N', last_name='T', dni='62000001',
        )
        no_type_user.person = person
        no_type_user.save()
        client = APIClient()
        client.force_authenticate(user=no_type_user)
        st = self._statement()
        response = client.post(
            reverse(self.URL),
            data={'user_id': admin_user.id, 'statement': st.id},
            format='json',
        )
        assert response.status_code == 201, response.data
        assert not PersonSwornStatement.objects.filter(person=other).exists()
        assert PersonSwornStatement.objects.filter(person=person).exists()

    def test_admin_signs_for_other(self, admin_client, person):
        from apps.users.models import CustomUser
        st = self._statement()
        target_person = Person.objects.create(name='Target', last_name='P', dni='61000000')
        target = CustomUser.objects.create_user(
            email='t@test.com', password='x', name='T', last_name='P', dni='61000000',
        )
        target.person = target_person
        target.save()
        response = admin_client.post(
            reverse(self.URL),
            data={'user_id': target.id, 'statement': st.id},
            format='json',
        )
        assert response.status_code == 201, response.data
        assert PersonSwornStatement.objects.filter(person=target_person).exists()


# Tests de seguridad: appointment-sworn-statement valida propiedad

@pytest.mark.django_db
class TestAppointmentSwornStatementSecurity:
    URL = 'appointment-sworn-statement-list'

    def _clase_activa(self):
        return SwornStatement.objects.create(
            text='Declaro sobre la clase.', statement_type='appointment', is_active=True,
        )

    def _appointment_for(self, person):
        from apps.appointments.models import Appointment
        return Appointment.objects.create(person=person)

    def test_anonymous_cannot_sign(self, person):
        """Firmar requiere autenticación (IsAuthenticated)."""
        st = self._clase_activa()
        appt = self._appointment_for(person)
        client = APIClient()
        response = client.post(
            reverse(self.URL),
            data={'appointment': appt.id, 'statement': st.id},
            format='json',
        )
        assert response.status_code in (401, 403)
        appt.refresh_from_db()
        assert appt.firmo_declaracion_clase is False

    def test_student_signs_own_appointment(self, student_client, student_user, person):
        """Un Student puede firmar la declaración de un turno propio -> 201 y flag en True."""
        student_user.person = person
        student_user.save()
        st = self._clase_activa()
        appt = self._appointment_for(person)
        response = student_client.post(
            reverse(self.URL),
            data={'appointment': appt.id, 'statement': st.id},
            format='json',
        )
        assert response.status_code == 201, response.data
        appt.refresh_from_db()
        assert appt.firmo_declaracion_clase is True

    def test_student_cannot_sign_other_appointment(self, student_client, student_user, person):
        """Regresión del vuln (Lola): un Student NO puede firmar el turno de otro alumno."""
        from apps.appointments.models import Appointment
        student_user.person = person
        student_user.save()
        other = Person.objects.create(name='Otro', last_name='Alumno', dni='60000000')
        st = self._clase_activa()
        other_appt = Appointment.objects.create(person=other)
        response = student_client.post(
            reverse(self.URL),
            data={'appointment': other_appt.id, 'statement': st.id},
            format='json',
        )
        assert response.status_code == 403, response.data
        other_appt.refresh_from_db()
        assert other_appt.firmo_declaracion_clase is False
        assert not AppointmentSwornStatement.objects.filter(appointment=other_appt).exists()

    def test_admin_signs_any_appointment(self, admin_client, person):
        """Admin/Super pueden firmar por cualquier turno -> 201."""
        st = self._clase_activa()
        appt = self._appointment_for(person)
        response = admin_client.post(
            reverse(self.URL),
            data={'appointment': appt.id, 'statement': st.id},
            format='json',
        )
        assert response.status_code == 201, response.data
        appt.refresh_from_db()
        assert appt.firmo_declaracion_clase is True

    def test_missing_appointment_returns_400(self, student_client, student_user, person):
        student_user.person = person
        student_user.save()
        st = self._clase_activa()
        response = student_client.post(
            reverse(self.URL),
            data={'statement': st.id},
            format='json',
        )
        assert response.status_code == 400

    def test_nonexistent_appointment_returns_404(self, student_client, student_user, person):
        student_user.person = person
        student_user.save()
        st = self._clase_activa()
        response = student_client.post(
            reverse(self.URL),
            data={'appointment': 999999, 'statement': st.id},
            format='json',
        )
        assert response.status_code == 404

    def test_authenticated_without_person_cannot_sign(self, student_client, person):
        """Un no-admin sin person asociada no puede firmar (403 controlado, no 500)."""
        # student_client (student_user) NO tiene person asignada.
        st = self._clase_activa()
        appt = self._appointment_for(person)
        response = student_client.post(
            reverse(self.URL),
            data={'appointment': appt.id, 'statement': st.id},
            format='json',
        )
        assert response.status_code == 403
        appt.refresh_from_db()
        assert appt.firmo_declaracion_clase is False


# Lectura acotada al dueño para Student, comentario Agostina)

@pytest.mark.django_db
class TestPersonSwornStatementReadScope:
    URL = 'person-sworn-statement-list'

    def _statement(self):
        return SwornStatement.objects.create(text='Declaración de prueba')

    def test_student_ve_solo_lo_propio(self, student_client, student_user, person):
        student_user.person = person
        student_user.save()
        other = Person.objects.create(name='Otro', last_name='P', dni='63000000')
        st = self._statement()
        PersonSwornStatement.objects.create(person=person, statement=st)
        PersonSwornStatement.objects.create(person=other, statement=st)
        resp = student_client.get(reverse(self.URL))
        assert resp.status_code == 200, resp.data
        assert {row['person'] for row in resp.data} == {person.id}

    def test_admin_ve_todo(self, admin_client, person):
        other = Person.objects.create(name='Otro', last_name='P', dni='63000001')
        st = self._statement()
        PersonSwornStatement.objects.create(person=person, statement=st)
        PersonSwornStatement.objects.create(person=other, statement=st)
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        assert len(resp.data) == 2

    def test_student_sin_person_devuelve_vacio_no_500(self, student_client, person):
        # student_user (vía student_client) no tiene person asignada.
        st = self._statement()
        PersonSwornStatement.objects.create(person=person, statement=st)
        resp = student_client.get(reverse(self.URL))
        assert resp.status_code == 200
        assert resp.data == []

    def test_anonimo_no_puede_leer(self, person):
        resp = APIClient().get(reverse(self.URL))
        assert resp.status_code in (401, 403)

    def test_student_retrieve_de_firma_ajena_es_404(self, student_client, student_user, person):
        student_user.person = person
        student_user.save()
        other = Person.objects.create(name='Otro', last_name='P', dni='63000002')
        st = self._statement()
        sig_other = PersonSwornStatement.objects.create(person=other, statement=st)
        resp = student_client.get(reverse(self.URL) + f'{sig_other.id}/')
        assert resp.status_code == 404


@pytest.mark.django_db
class TestAppointmentSwornStatementReadScope:
    URL = 'appointment-sworn-statement-list'

    def _statement(self):
        return SwornStatement.objects.create(
            text='Declaración de clase', statement_type='appointment', is_active=True,
        )

    def _appointment(self, person):
        from apps.appointments.models import Appointment
        return Appointment.objects.create(person=person)

    def test_student_ve_solo_sus_turnos(self, student_client, student_user, person):
        student_user.person = person
        student_user.save()
        other = Person.objects.create(name='Otro', last_name='P', dni='64000000')
        st = self._statement()
        my_appt = self._appointment(person)
        other_appt = self._appointment(other)
        AppointmentSwornStatement.objects.create(appointment=my_appt, statement=st)
        AppointmentSwornStatement.objects.create(appointment=other_appt, statement=st)
        resp = student_client.get(reverse(self.URL))
        assert resp.status_code == 200, resp.data
        assert {row['appointment_id'] for row in resp.data} == {my_appt.id}

    def test_student_filtrando_turno_ajeno_vacio(self, student_client, student_user, person):
        student_user.person = person
        student_user.save()
        other = Person.objects.create(name='Otro', last_name='P', dni='64000001')
        st = self._statement()
        other_appt = self._appointment(other)
        AppointmentSwornStatement.objects.create(appointment=other_appt, statement=st)
        resp = student_client.get(reverse(self.URL) + f'?appointment={other_appt.id}')
        assert resp.status_code == 200
        assert resp.data == []

    def test_admin_ve_todo(self, admin_client, person):
        other = Person.objects.create(name='Otro', last_name='P', dni='64000002')
        st = self._statement()
        AppointmentSwornStatement.objects.create(appointment=self._appointment(person), statement=st)
        AppointmentSwornStatement.objects.create(appointment=self._appointment(other), statement=st)
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        assert len(resp.data) == 2
