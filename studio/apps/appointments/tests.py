import pytest
from datetime import date, time, timedelta
from django.urls import reverse
from django.utils import timezone
from .models import Appointment
from apps.slots.models import Slot
from apps.people.models import PersonActivePlan


@pytest.mark.django_db
class TestAppointmentSoftDelete:

    def test_delete_sets_deleted(self, slot, person):
        appointment = Appointment.objects.create(person=person, slot=slot)
        appointment.delete()
        appointment.refresh_from_db()
        assert appointment.deleted is not None

    def test_objects_hides_deleted(self, slot, person):
        appointment = Appointment.objects.create(person=person, slot=slot)
        appointment.delete()
        assert not Appointment.objects.filter(pk=appointment.pk).exists()

    def test_all_objects_includes_deleted(self, slot, person):
        appointment = Appointment.objects.create(person=person, slot=slot)
        appointment.delete()
        assert Appointment.all_objects.filter(pk=appointment.pk).exists()

    def test_all_objects_dead_returns_deleted(self, slot, person):
        appointment = Appointment.objects.create(person=person, slot=slot)
        appointment.delete()
        assert Appointment.all_objects.dead().filter(pk=appointment.pk).exists()

    def test_all_objects_alive_excludes_deleted(self, slot, person):
        appointment = Appointment.objects.create(person=person, slot=slot)
        appointment.delete()
        assert not Appointment.all_objects.alive().filter(pk=appointment.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user, slot, person):
        appointment = Appointment.objects.create(person=person, slot=slot)
        appointment.delete()
        qs = Appointment.all_objects.for_user(admin_user)
        assert qs.filter(pk=appointment.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user, slot, person):
        appointment = Appointment.objects.create(person=person, slot=slot)
        appointment.delete()
        qs = Appointment.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=appointment.pk).exists()

    def test_restore(self, slot, person):
        appointment = Appointment.objects.create(person=person, slot=slot)
        appointment.delete()
        appointment.restore()
        appointment.refresh_from_db()
        assert appointment.deleted is None

    def test_hard_delete_removes_from_db(self, slot, person):
        appointment = Appointment.objects.create(person=person, slot=slot)
        pk = appointment.pk
        appointment.hard_delete()
        assert not Appointment.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestAppointmentsViewForUser:
    URL = 'appointments-list'

    def test_admin_list_excludes_deleted(self, admin_client, slot, person):
        # la vista /appointments/ no muestra turnos eliminados para NINGÚN
        # rol, ni siquiera admin/super (antes el admin sí los veía vía for_user).
        appointment = Appointment.objects.create(person=person, slot=slot)
        appointment.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert appointment.id not in ids

    def test_consultor_list_excludes_deleted(self, consultor_client, slot, person):
        appointment = Appointment.objects.create(person=person, slot=slot)
        appointment.delete()
        response = consultor_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert appointment.id not in ids

    def test_delete_endpoint_is_soft_delete(self, admin_client, slot, person, monkeypatch):
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kwargs: None)
        appointment = Appointment.objects.create(person=person, slot=slot)
        url = reverse('appointments-detail', args=[appointment.pk])
        response = admin_client.delete(url, data={'code': 'admin'}, format='json')
        assert response.status_code == 204
        assert Appointment.all_objects.filter(pk=appointment.pk).exists()
        appointment.refresh_from_db()
        assert appointment.deleted is not None

    def test_create_appointment_success(self, admin_client, slot, person, monkeypatch):
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kwargs: None)
        from apps.appointments.views import AppointmentsViewSet
        monkeypatch.setattr(AppointmentsViewSet, "send_waitlist_message", lambda self, app, code: None)
        url = reverse(self.URL)
        data = {'slot_id': slot.id, 'person_id': person.id, 'code': 'admin'}
        initial_availability = slot.availability
        response = admin_client.post(url, data=data, format='json')
        assert response.status_code == 201
        assert Appointment.objects.filter(slot=slot, person=person).exists()
        slot.refresh_from_db()
        assert slot.availability == initial_availability - 1

    def test_create_appointment_limit_exceeded(self, admin_client, slot_with_activity, person, plans_subtype_a, monkeypatch):
        """ el cupo lo impone ahora sessions_remaining, no un conteo de turnos.
        Plan de la actividad sin sesiones restantes -> 400 'sin sesiones'."""
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kwargs: None)
        PersonActivePlan.objects.create(
            person=person,
            plans_subtype=plans_subtype_a,
            exp_date=date.today() + timedelta(days=30),
            sessions_total=3,
            sessions_remaining=0,
        )
        url = reverse(self.URL)
        data = {'slot_id': slot_with_activity.id, 'person_id': person.id, 'code': 'admin'}
        response = admin_client.post(url, data=data, format='json')
        assert response.status_code == 400
        assert "sesiones" in response.data['detail']
        assert not Appointment.objects.filter(slot=slot_with_activity, person=person).exists()

    def test_create_appointment_no_active_plan_is_unlimited(self, admin_client, slot, person, status, room, monkeypatch):
        """ sin PersonActivePlan activo, no hay tope de turnos (comportamiento legacy)."""
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kwargs: None)
        for i in range(3):
            other_slot = Slot.objects.create(
                status=status,
                room=room,
                date=date.today() + timedelta(days=2 + i),
                start_time=time(9, 0),
                end_time=time(10, 0),
                availability=10,
            )
            Appointment.objects.create(person=person, slot=other_slot)
        url = reverse(self.URL)
        data = {'slot_id': slot.id, 'person_id': person.id, 'code': 'admin'}
        response = admin_client.post(url, data=data, format='json')
        assert response.status_code == 201

    def test_create_appointment_limit_from_sessions_remaining(self, admin_client, slot_with_activity, person, plans_subtype_a, monkeypatch):
        """ el tope surge de sessions_remaining == 0 del PersonActivePlan de la
        actividad (ya no de un conteo de turnos previos)."""
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kwargs: None)
        PersonActivePlan.objects.create(
            person=person,
            plans_subtype=plans_subtype_a,
            exp_date=date.today() + timedelta(days=30),
            sessions_total=2,
            sessions_remaining=0,
        )
        url = reverse(self.URL)
        data = {'slot_id': slot_with_activity.id, 'person_id': person.id, 'code': 'admin'}
        response = admin_client.post(url, data=data, format='json')
        assert response.status_code == 400
        assert "sesiones" in response.data['detail']

    def test_create_appointment_slot_full(self, admin_client, slot, person, monkeypatch):
        from apps.actions.models import Action
        from apps.status.models import Status
        monkeypatch.setattr(Action.objects, "create", lambda **kwargs: None)
        full_status, _ = Status.objects.get_or_create(id=2, defaults={'status': 'Lleno'})
        slot.status = full_status
        slot.save()
        url = reverse(self.URL)
        data = {'slot_id': slot.id, 'person_id': person.id, 'code': 'admin'}
        response = admin_client.post(url, data=data, format='json')
        assert response.status_code == 400
        assert "cupo en este horario está lleno" in response.data['detail']

    def test_filter_by_person_id(self, admin_client, slot, person, monkeypatch):
        from apps.people.models import Person
        other = Person.objects.create(name='Otro', last_name='Persona', dni='88888888')
        Appointment.objects.create(person=person, slot=slot)
        Appointment.objects.create(person=other, slot=slot)
        response = admin_client.get(reverse(self.URL), {'person_id': person.id})
        assert response.status_code == 200
        person_ids = {a['person'] for a in response.data}
        assert person_ids == {person.id}


@pytest.mark.django_db
class TestEnrollmentCheckView:
    URL = 'enrollment-check-list'

    def test_missing_params_returns_400(self, admin_client):
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 400

    def test_slot_without_activity_returns_400(self, admin_client, slot, person):
        response = admin_client.get(reverse(self.URL), {'person': person.id, 'slot': slot.id})
        assert response.status_code == 400
        assert 'actividad' in response.data['detail']

    def test_covered_returns_true_with_active_plan(
        self, admin_client, person, slot_with_activity, person_active_plan
    ):
        response = admin_client.get(reverse(self.URL), {
            'person': person.id,
            'slot': slot_with_activity.id,
        })
        assert response.status_code == 200
        assert response.data['covered'] is True
        assert 'active_plan' in response.data

    def test_not_covered_returns_required_plans_subtypes(
        self, admin_client, person, slot_with_activity, plans_subtype_a
    ):
        # persona sin plan activo
        response = admin_client.get(reverse(self.URL), {
            'person': person.id,
            'slot': slot_with_activity.id,
        })
        assert response.status_code == 200
        assert response.data['covered'] is False
        assert 'required_plans_subtypes' in response.data

    def test_expired_plan_not_covered(self, admin_client, person, slot_with_activity, plans_subtype_a):
        past = timezone.now().date() - timedelta(days=1)
        PersonActivePlan.objects.create(
            person=person, plans_subtype=plans_subtype_a,
            exp_date=past, sessions_total=10, sessions_remaining=5,
        )
        response = admin_client.get(reverse(self.URL), {
            'person': person.id, 'slot': slot_with_activity.id,
        })
        assert response.status_code == 200
        assert response.data['covered'] is False

    def test_no_sessions_not_covered(self, admin_client, person, slot_with_activity, plans_subtype_a):
        future = timezone.now().date() + timedelta(days=30)
        PersonActivePlan.objects.create(
            person=person, plans_subtype=plans_subtype_a,
            exp_date=future, sessions_total=10, sessions_remaining=0,
        )
        response = admin_client.get(reverse(self.URL), {
            'person': person.id, 'slot': slot_with_activity.id,
        })
        assert response.status_code == 200
        assert response.data['covered'] is False

    def test_slot_not_found_returns_404(self, admin_client, person):
        response = admin_client.get(reverse(self.URL), {'person': person.id, 'slot': 99999})
        assert response.status_code == 404


# CalendarViewSet

@pytest.mark.django_db
class TestCalendarViewSet:
    URL = 'calendar-list'

    @pytest.fixture
    def slot_with_date(self, status, room):
        return Slot.objects.create(
            status=status, room=room,
            date=date(2026, 6, 1),
            start_time=time(9, 0), end_time=time(10, 0),
            availability=5,
        )

    @pytest.fixture
    def slot_with_date_b(self, status, room):
        return Slot.objects.create(
            status=status, room=room,
            date=date(2026, 6, 2),
            start_time=time(10, 0), end_time=time(11, 0),
            availability=8,
        )

    def test_returns_200(self, admin_client):
        response = admin_client.get(
            reverse(self.URL), {'date_from': '2026-06-01', 'date_to': '2026-06-01'},
        )
        assert response.status_code == 200

    def test_response_is_list_of_days(self, admin_client, slot_with_date):
        response = admin_client.get(
            reverse(self.URL), {'date_from': '2026-06-01', 'date_to': '2026-06-02'},
        )
        assert response.status_code == 200
        assert isinstance(response.data, list)
        assert len(response.data) == 2

    def test_each_day_has_date_and_slots(self, admin_client, slot_with_date):
        response = admin_client.get(
            reverse(self.URL), {'date_from': '2026-06-01', 'date_to': '2026-06-01'},
        )
        day = response.data[0]
        assert 'date' in day
        assert 'slots' in day
        assert day['date'] == '2026-06-01'

    def test_slot_appears_in_correct_day(self, admin_client, slot_with_date, slot_with_date_b):
        response = admin_client.get(
            reverse(self.URL), {'date_from': '2026-06-01', 'date_to': '2026-06-02'},
        )
        day1_slot_ids = [s['id'] for s in response.data[0]['slots']]
        day2_slot_ids = [s['id'] for s in response.data[1]['slots']]
        assert slot_with_date.id in day1_slot_ids
        assert slot_with_date_b.id in day2_slot_ids
        assert slot_with_date_b.id not in day1_slot_ids

    def test_appointments_embedded_in_slot(self, admin_client, slot_with_date, person):
        Appointment.objects.create(person=person, slot=slot_with_date)
        response = admin_client.get(
            reverse(self.URL), {'date_from': '2026-06-01', 'date_to': '2026-06-01'},
        )
        appts = response.data[0]['slots'][0]['appointments']
        assert len(appts) == 1
        assert appts[0]['person_id'] == person.id

    def test_soft_deleted_appointment_not_included(self, admin_client, slot_with_date, person):
        appt = Appointment.objects.create(person=person, slot=slot_with_date)
        appt.delete()
        response = admin_client.get(
            reverse(self.URL), {'date_from': '2026-06-01', 'date_to': '2026-06-01'},
        )
        assert response.data[0]['slots'][0]['appointments'] == []

    def test_soft_deleted_slot_not_included(self, admin_client, slot_with_date):
        slot_with_date.delete()
        response = admin_client.get(
            reverse(self.URL), {'date_from': '2026-06-01', 'date_to': '2026-06-01'},
        )
        assert response.data[0]['slots'] == []

    def test_invalid_date_format_returns_400(self, admin_client):
        response = admin_client.get(
            reverse(self.URL), {'date_from': '01-06-2026', 'date_to': '2026-06-07'},
        )
        assert response.status_code == 400

    def test_date_from_after_date_to_returns_400(self, admin_client):
        response = admin_client.get(
            reverse(self.URL), {'date_from': '2026-06-10', 'date_to': '2026-06-01'},
        )
        assert response.status_code == 400

    def test_unauthenticated_returns_403(self):
        from rest_framework.test import APIClient
        response = APIClient().get(
            reverse(self.URL), {'date_from': '2026-06-01', 'date_to': '2026-06-07'},
        )
        assert response.status_code in (401, 403)


# UpcomingAppointmentsViewSet
# Por qué: devuelve solo reservas con slot.date >= hoy para mostrar agenda futura.
# Se verifica que pasadas no aparecen, que el filtro person_id funciona,
# y que las eliminadas (soft delete) no se incluyen.

@pytest.mark.django_db
class TestUpcomingAppointments:
    URL = 'upcoming-appointments-list'

    def test_returns_only_future_appointments(self, admin_client, slot_future, slot_past, person):
        appt_future = Appointment.objects.create(person=person, slot=slot_future)
        Appointment.objects.create(person=person, slot=slot_past)
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [a['id'] for a in response.data]
        assert appt_future.id in ids

    def test_past_appointment_not_included(self, admin_client, slot_past, person):
        appt_past = Appointment.objects.create(person=person, slot=slot_past)
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [a['id'] for a in response.data]
        assert appt_past.id not in ids

    def test_filter_by_person_id(self, admin_client, slot_future, person):
        from apps.people.models import Person
        other = Person.objects.create(name='Otro', last_name='Test', dni='77777777')
        appt_mine = Appointment.objects.create(person=person, slot=slot_future)
        Appointment.objects.create(person=other, slot=slot_future)
        response = admin_client.get(reverse(self.URL), {'person_id': person.id})
        ids = [a['id'] for a in response.data]
        assert appt_mine.id in ids
        assert all(a['person'] == person.id for a in response.data)

    def test_soft_deleted_not_included(self, admin_client, slot_future, person):
        appt = Appointment.objects.create(person=person, slot=slot_future)
        appt.delete()
        response = admin_client.get(reverse(self.URL))
        ids = [a['id'] for a in response.data]
        assert appt.id not in ids

    def test_ordered_by_date_asc(self, admin_client, status, room, person):
        s1 = Slot.objects.create(status=status, room=room, date=date.today() + timedelta(days=5),
                                  start_time=time(9, 0), end_time=time(10, 0), availability=5)
        s2 = Slot.objects.create(status=status, room=room, date=date.today() + timedelta(days=2),
                                  start_time=time(9, 0), end_time=time(10, 0), availability=5)
        Appointment.objects.create(person=person, slot=s1)
        Appointment.objects.create(person=person, slot=s2)
        response = admin_client.get(reverse(self.URL), {'person_id': person.id})
        dates = [a['slot'] for a in response.data]
        assert dates == sorted(dates)

    def test_unauthenticated_returns_403(self):
        from rest_framework.test import APIClient
        response = APIClient().get(reverse(self.URL))
        assert response.status_code in (401, 403)


# PastAppointmentsViewSet
# Por qué: historial de clases pasadas por alumno. Las futuras no deben aparecer.

@pytest.mark.django_db
class TestPastAppointments:
    URL = 'past-appointments-list'

    def test_returns_only_past_appointments(self, admin_client, slot_future, slot_past, person):
        Appointment.objects.create(person=person, slot=slot_future)
        appt_past = Appointment.objects.create(person=person, slot=slot_past)
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [a['id'] for a in response.data]
        assert appt_past.id in ids

    def test_future_appointment_not_included(self, admin_client, slot_future, person):
        appt_future = Appointment.objects.create(person=person, slot=slot_future)
        response = admin_client.get(reverse(self.URL))
        ids = [a['id'] for a in response.data]
        assert appt_future.id not in ids

    def test_filter_by_person_id(self, admin_client, slot_past, person):
        from apps.people.models import Person
        other = Person.objects.create(name='Otro', last_name='Test', dni='66666666')
        appt_mine = Appointment.objects.create(person=person, slot=slot_past)
        Appointment.objects.create(person=other, slot=slot_past)
        response = admin_client.get(reverse(self.URL), {'person_id': person.id})
        ids = [a['id'] for a in response.data]
        assert appt_mine.id in ids
        assert all(a['person'] == person.id for a in response.data)

    def test_soft_deleted_not_included(self, admin_client, slot_past, person):
        appt = Appointment.objects.create(person=person, slot=slot_past)
        appt.delete()
        response = admin_client.get(reverse(self.URL))
        ids = [a['id'] for a in response.data]
        assert appt.id not in ids

    def test_unauthenticated_returns_403(self):
        from rest_framework.test import APIClient
        response = APIClient().get(reverse(self.URL))
        assert response.status_code in (401, 403)


# Cancel action
# Por qué: la cancelación tiene una regla de negocio crítica: no se puede
# cancelar con menos de CANCEL_HOURS_LIMIT horas de anticipación.
# Se verifica el límite, que libera el slot, y que registra audit trail.

@pytest.mark.django_db
class TestCancelAction:

    def _make_slot_hours_from_now(self, status, room, hours_ahead):
        from datetime import datetime
        dt = datetime.now() + timedelta(hours=hours_ahead)
        return Slot.objects.create(
            status=status,
            room=room,
            date=dt.date(),
            start_time=dt.time().replace(second=0, microsecond=0),
            end_time=(dt + timedelta(hours=1)).time().replace(second=0, microsecond=0),
            availability=10,
        )

    def test_cancel_with_enough_time_succeeds(self, admin_client, status, room, person, monkeypatch):
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kwargs: None)
        slot = self._make_slot_hours_from_now(status, room, hours_ahead=5)
        initial_avail = slot.availability
        appt = Appointment.objects.create(person=person, slot=slot)
        url = reverse('appointments-cancel', args=[appt.pk])
        response = admin_client.post(url, data={'code': 'admin'}, format='json')
        assert response.status_code == 204
        appt.refresh_from_db()
        assert appt.deleted is not None
        slot.refresh_from_db()
        assert slot.availability == initial_avail + 1

    def test_cancel_within_limit_returns_400(self, status, room, person, user_types, monkeypatch):
        from apps.actions.models import Action
        from apps.users.models import CustomUser
        from rest_framework.test import APIClient
        monkeypatch.setattr(Action.objects, "create", lambda **kwargs: None)
        # El límite de 2 hs aplica a ESTUDIANTES: alumno con 1h -> 400.
        student = CustomUser.objects.create_user(
            email='stud_lim@test.com', password='p', name='S', last_name='L',
            dni='45670009', tipo_usuario=user_types['student'],
        )
        student.person = person
        student.save(update_fields=['person'])
        client = APIClient()
        client.force_authenticate(user=student)
        slot = self._make_slot_hours_from_now(status, room, hours_ahead=1)
        appt = Appointment.objects.create(person=person, slot=slot)
        url = reverse('appointments-cancel', args=[appt.pk])
        response = client.post(url, data={'code': student.code}, format='json')
        assert response.status_code == 400
        assert 'anticipación' in response.data['detail']

    def test_cancel_does_not_hard_delete(self, admin_client, status, room, person, monkeypatch):
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kwargs: None)
        slot = self._make_slot_hours_from_now(status, room, hours_ahead=5)
        appt = Appointment.objects.create(person=person, slot=slot)
        url = reverse('appointments-cancel', args=[appt.pk])
        admin_client.post(url, data={'code': 'admin'}, format='json')
        assert Appointment.all_objects.filter(pk=appt.pk).exists()

    def test_cancel_invalid_code_returns_error(self, admin_client, status, room, person):
        slot = self._make_slot_hours_from_now(status, room, hours_ahead=5)
        appt = Appointment.objects.create(person=person, slot=slot)
        url = reverse('appointments-cancel', args=[appt.pk])
        response = admin_client.post(url, data={'code': 'INVALID_CODE_XYZ'}, format='json')
        assert response.status_code == 400

    def test_unauthenticated_returns_403(self, status, room, person):
        from rest_framework.test import APIClient
        slot = self._make_slot_hours_from_now(status, room, hours_ahead=5)
        appt = Appointment.objects.create(person=person, slot=slot)
        url = reverse('appointments-cancel', args=[appt.pk])
        response = APIClient().post(url, data={'code': 'admin'}, format='json')
        assert response.status_code in (401, 403)


# is_student en appointments
# Por qué: un Admin/Consultor/Super con is_student=True debe poder acceder a
# upcoming/past/appointments como si fuera alumno, viendo solo sus propias
# reservas (scoped por person_id del usuario).

@pytest.mark.django_db
class TestIsStudentAppointmentAccess:

    @pytest.fixture
    def admin_student_user(self, user_types, person):
        """Admin con is_student=True vinculado a un Person."""
        from apps.users.models import CustomUser
        user = CustomUser.objects.create_user(
            email='admin_est@test.com', password='pass123',
            name='Admin', last_name='Est', dni='88880001',
            tipo_usuario=user_types['admin'],
            is_student=True,
        )
        user.person = person
        user.save(update_fields=['person'])
        return user

    @pytest.fixture
    def admin_student_client(self, admin_student_user):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=admin_student_user)
        return client

    @pytest.fixture
    def other_person(self, db):
        from apps.people.models import Person
        return Person.objects.create(name='Otro', last_name='Alumno', dni='88880002')

    def test_admin_student_can_access_upcoming(self, admin_student_client):
        response = admin_student_client.get(reverse('upcoming-appointments-list'))
        assert response.status_code == 200

    def test_admin_student_sees_only_own_upcoming(self, admin_student_client, admin_student_user, slot_future, person, other_person, status, room):
        """Admin con is_student solo ve sus propias reservas en upcoming."""
        own_appt = Appointment.objects.create(person=person, slot=slot_future)
        other_slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=4),
            start_time=time(10, 0), end_time=time(11, 0), availability=5,
        )
        Appointment.objects.create(person=other_person, slot=other_slot)

        response = admin_student_client.get(reverse('upcoming-appointments-list'))
        assert response.status_code == 200
        pks = [a['id'] for a in response.data]
        assert own_appt.pk in pks
        assert all(a['person'] == person.pk for a in response.data)

    def test_admin_student_can_access_past(self, admin_student_client):
        response = admin_student_client.get(reverse('past-appointments-list'))
        assert response.status_code == 200

    def test_admin_student_sees_only_own_past(self, admin_student_client, slot_past, person, other_person, status, room):
        """Admin con is_student solo ve sus propias reservas en past."""
        own_appt = Appointment.objects.create(person=person, slot=slot_past)
        other_slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() - timedelta(days=4),
            start_time=time(10, 0), end_time=time(11, 0), availability=5,
        )
        Appointment.objects.create(person=other_person, slot=other_slot)

        response = admin_student_client.get(reverse('past-appointments-list'))
        pks = [a['id'] for a in response.data]
        assert own_appt.pk in pks
        assert all(a['person'] == person.pk for a in response.data)

    def test_admin_without_flag_blocked_from_upcoming(self, admin_client):
        """Admin sin is_student sigue viendo todos (no filtrado)."""
        response = admin_client.get(reverse('upcoming-appointments-list'))
        assert response.status_code == 200

    def test_admin_student_can_access_appointments_list(self, admin_student_client):
        response = admin_student_client.get(reverse('appointments-list'))
        assert response.status_code == 200

    def test_admin_student_appointments_scoped_to_own_person(self, admin_student_client, slot_future, person, other_person, status, room):
        """En /appointments/ el admin-alumno solo ve las suyas."""
        own_appt = Appointment.objects.create(person=person, slot=slot_future)
        other_slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=2),
            start_time=time(11, 0), end_time=time(12, 0), availability=5,
        )
        Appointment.objects.create(person=other_person, slot=other_slot)

        response = admin_student_client.get(reverse('appointments-list'))
        pks = [a['id'] for a in response.data]
        assert own_appt.pk in pks
        assert all(a['person'] == person.pk for a in response.data)


# Update: audit log usa slot.date, no week_day
# Por qué: el campo week_day fue eliminado del modelo Slot y reemplazado por
# date (DateField). El método update de AppointmentsViewSet construía el audit
# log usando old_slot.week_day y new_slot.week_day, lo que lanzaba
# AttributeError. El fix es derivar el nombre del día desde slot.date.weekday().

@pytest.mark.django_db
class TestAppointmentUpdateAuditLog:

    def test_update_audit_log_uses_date_not_week_day(self, admin_client, slot, person, monkeypatch):
        """
        PUT /appointments/{id}/ debe responder 200 y construir old_value/new_value
        con el nombre del día en español derivado de slot.date, sin AttributeError.

        Antes del fix: AttributeError: 'Slot' object has no attribute 'week_day'
        al construir old_value en la línea ~260 de views.py.
        """
        from apps.actions.models import Action

        # Capturamos los kwargs pasados a Action.objects.create para poder
        # verificar el contenido sin depender de ArrayField (PostgreSQL-only).
        captured = []

        def fake_action_create(**kwargs):
            captured.append(kwargs)

        monkeypatch.setattr(Action.objects, "create", fake_action_create)

        appointment = Appointment.objects.create(person=person, slot=slot)
        url = reverse('appointments-detail', args=[appointment.pk])

        response = admin_client.put(
            url,
            data={'slot_id': slot.id, 'person_id': person.id, 'code': 'admin'},
            format='json',
        )

        assert response.status_code == 200

        # Debe haberse registrado exactamente una acción de Actualizar
        assert len(captured) == 1
        action_kwargs = captured[0]
        assert action_kwargs['action'] == 'Actualizar'
        assert action_kwargs['target'] == 'Turno'

        # El nombre del día debe derivarse de slot.date (no de week_day)
        day_names = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        expected_day = day_names[slot.date.weekday()]

        old_turno = next(f['value'] for f in action_kwargs['old_value'] if f['field'] == 'Turno')
        new_turno = next(f['value'] for f in action_kwargs['new_value'] if f['field'] == 'Turno')

        assert expected_day in old_turno, f"Se esperaba '{expected_day}' en old_value turno, got: {old_turno!r}"
        assert expected_day in new_turno, f"Se esperaba '{expected_day}' en new_value turno, got: {new_turno!r}"


@pytest.mark.django_db
def test_appointment_fixed_slot_fk(person, room, week):
    from datetime import date, time
    from apps.slots.models import SlotTemplate, FixedSlot
    from apps.appointments.models import Appointment

    t = SlotTemplate.objects.create(start_time=time(9, 0), end_time=time(10, 0), room=room, availability=10)
    fs = FixedSlot.objects.create(person=person, template=t, start_date=date.today())

    appt = Appointment.objects.create(person=person, fixed_slot=fs)
    assert appt.fixed_slot == fs
    assert list(fs.appointments.all()) == [appt]

    manual = Appointment.objects.create(person=person)
    assert manual.fixed_slot is None


@pytest.mark.django_db
class TestAppointmentConsumedPlan:
    def test_appointment_guarda_consumed_plan(self, person, slot_with_activity, person_active_plan):
        from apps.appointments.models import Appointment
        appt = Appointment.objects.create(
            person=person, slot=slot_with_activity, reserved=False,
            consumed_plan=person_active_plan,
        )
        appt.refresh_from_db()
        assert appt.consumed_plan_id == person_active_plan.id


@pytest.mark.django_db
class TestCreateConsumeSession:
    URL = 'appointments-list'

    @pytest.fixture(autouse=True)
    def _mock_action(self, monkeypatch):
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kw: None)

    def _plan(self, person, plans_subtype_a, sessions):
        from datetime import timedelta
        from django.utils import timezone
        from apps.people.models import PersonActivePlan
        return PersonActivePlan.objects.create(
            person=person, plans_subtype=plans_subtype_a,
            exp_date=timezone.now().date() + timedelta(days=30),
            sessions_total=sessions, sessions_remaining=sessions,
        )

    def _post(self, admin_client, person, slot):
        return admin_client.post(reverse(self.URL), data={
            'person_id': person.id, 'slot_id': slot.id, 'code': 'admin',
        }, format='json')

    def test_reserva_con_plan_descuenta_una_sesion(self, admin_client, person, slot_with_activity, plans_subtype_a):
        plan = self._plan(person, plans_subtype_a, 10)
        resp = self._post(admin_client, person, slot_with_activity)
        assert resp.status_code == 201, resp.data
        plan.refresh_from_db()
        assert plan.sessions_remaining == 9
        from apps.appointments.models import Appointment
        appt = Appointment.objects.get(person=person, slot=slot_with_activity)
        assert appt.consumed_plan_id == plan.id

    def test_reserva_sin_sesiones_devuelve_400(self, admin_client, person, slot_with_activity, plans_subtype_a):
        self._plan(person, plans_subtype_a, 0)
        resp = self._post(admin_client, person, slot_with_activity)
        assert resp.status_code == 400
        from apps.appointments.models import Appointment
        assert not Appointment.objects.filter(person=person, slot=slot_with_activity).exists()

    def test_reserva_sin_plan_no_descuenta(self, admin_client, person, slot_with_activity):
        resp = self._post(admin_client, person, slot_with_activity)
        assert resp.status_code == 201, resp.data
        from apps.appointments.models import Appointment
        appt = Appointment.objects.get(person=person, slot=slot_with_activity)
        assert appt.consumed_plan_id is None

    def test_consumed_plan_enviado_por_cliente_es_ignorado(self, admin_client, person, slot, person_active_plan):
        # slot (sin activity_subtype) => find_consumable_plan devuelve None,
        # el bloque "if plan is not None" del view nunca corre. Un cliente
        # malicioso no debe poder setear consumed_plan directo en el body.
        resp = admin_client.post(reverse(self.URL), data={
            'person_id': person.id, 'slot_id': slot.id, 'code': 'admin',
            'consumed_plan': person_active_plan.id,
        }, format='json')
        assert resp.status_code == 201, resp.data
        from apps.appointments.models import Appointment
        appt = Appointment.objects.get(person=person, slot=slot)
        assert appt.consumed_plan_id is None


@pytest.mark.django_db
class TestCancelRefundsSession:
    @pytest.fixture(autouse=True)
    def _mock_action(self, monkeypatch):
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kw: None)

    def _appt_con_plan(self, person, slot_with_activity, person_active_plan):
        from apps.appointments.models import Appointment
        return Appointment.objects.create(
            person=person, slot=slot_with_activity, reserved=False,
            consumed_plan=person_active_plan,
        )

    def test_destroy_devuelve_sesion(self, admin_client, person, slot_with_activity, person_active_plan):
        appt = self._appt_con_plan(person, slot_with_activity, person_active_plan)
        antes = person_active_plan.sessions_remaining
        resp = admin_client.delete(reverse('appointments-detail', args=[appt.id]),
                                   data={'code': 'admin'}, format='json')
        assert resp.status_code == 204
        person_active_plan.refresh_from_db()
        assert person_active_plan.sessions_remaining == antes + 1

    def test_doble_destroy_no_duplica_devolucion(self, admin_client, person, slot_with_activity, person_active_plan):
        appt = self._appt_con_plan(person, slot_with_activity, person_active_plan)
        antes = person_active_plan.sessions_remaining
        url = reverse('appointments-detail', args=[appt.id])
        resp1 = admin_client.delete(url, data={'code': 'admin'}, format='json')
        resp2 = admin_client.delete(url, data={'code': 'admin'}, format='json')
        assert resp1.status_code == 204
        assert resp2.status_code == 404
        person_active_plan.refresh_from_db()
        assert person_active_plan.sessions_remaining == antes + 1

    def test_cancel_devuelve_sesion(self, admin_client, person, person_active_plan, status, room):
        # slot_future_with_activity no existe como fixture: se crea acá,
        # suficientemente en el futuro para pasar CANCEL_HOURS_LIMIT.
        from apps.appointments.models import Appointment
        slot_future_with_activity = Slot.objects.create(
            status=status,
            room=room,
            date=date.today() + timedelta(days=7),
            start_time=time(9, 0),
            end_time=time(10, 0),
            availability=10,
            activity_subtype=person_active_plan.plans_subtype.activity_subtype,
        )
        appt = Appointment.objects.create(
            person=person, slot=slot_future_with_activity, reserved=False,
            consumed_plan=person_active_plan,
        )
        antes = person_active_plan.sessions_remaining
        resp = admin_client.post(reverse('appointments-cancel', args=[appt.id]),
                                 data={'code': 'admin'}, format='json')
        assert resp.status_code == 204
        person_active_plan.refresh_from_db()
        assert person_active_plan.sessions_remaining == antes + 1

    def test_doble_cancel_no_duplica_devolucion(self, admin_client, person, person_active_plan, status, room):
        from apps.appointments.models import Appointment
        slot_future_with_activity = Slot.objects.create(
            status=status,
            room=room,
            date=date.today() + timedelta(days=7),
            start_time=time(9, 0),
            end_time=time(10, 0),
            availability=10,
            activity_subtype=person_active_plan.plans_subtype.activity_subtype,
        )
        appt = Appointment.objects.create(
            person=person, slot=slot_future_with_activity, reserved=False,
            consumed_plan=person_active_plan,
        )
        antes = person_active_plan.sessions_remaining
        url = reverse('appointments-cancel', args=[appt.id])
        resp1 = admin_client.post(url, data={'code': 'admin'}, format='json')
        resp2 = admin_client.post(url, data={'code': 'admin'}, format='json')
        assert resp1.status_code == 204
        assert resp2.status_code == 404
        person_active_plan.refresh_from_db()
        assert person_active_plan.sessions_remaining == antes + 1


@pytest.mark.django_db
class TestAppointmentUpdateSlotSwapNullKAN168:
    """Cambiar el slot de un appointment hacia un slot con availability NULL no debe
    romper (500)."""

    @pytest.fixture(autouse=True)
    def _mock_action(self, monkeypatch):
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kw: None)

    def test_cambio_a_slot_con_availability_nula_no_500(self, admin_client, person, status, room):
        from apps.slots.models import Slot
        from apps.appointments.models import Appointment
        d = date.today() + timedelta(days=3)
        slot_a = Slot.objects.create(
            status=status, room=room, date=d,
            start_time=time(9, 0), end_time=time(10, 0), availability=5,
        )
        slot_b = Slot.objects.create(
            status=status, room=room, date=d,
            start_time=time(11, 0), end_time=time(12, 0),
        )  # availability=None
        appt = Appointment.objects.create(person=person, slot=slot_a, reserved=False)
        resp = admin_client.put(
            reverse('appointments-detail', args=[appt.pk]),
            data={'person_id': person.id, 'slot_id': slot_b.id, 'code': 'admin'},
            format='json',
        )
        assert resp.status_code == 200, resp.data


@pytest.mark.django_db
class TestCalendarPlanExpDateKAN252:
    """Calendar expone por alumno plan_sub_type ({id,name}) y exp_date del plan
    vigente con sesiones (el de exp_date más lejano); null si no hay."""
    URL = 'calendar-list'

    @pytest.fixture
    def slot_cal(self, status, room):
        return Slot.objects.create(
            status=status, room=room, date=date(2026, 6, 1),
            start_time=time(9, 0), end_time=time(10, 0), availability=5,
        )

    def _plan(self, person, plans_subtype_a, exp_days, sessions):
        from datetime import timedelta
        from django.utils import timezone
        from apps.people.models import PersonActivePlan
        return PersonActivePlan.objects.create(
            person=person, plans_subtype=plans_subtype_a,
            exp_date=timezone.now().date() + timedelta(days=exp_days),
            sessions_total=sessions, sessions_remaining=sessions,
        )

    def _appt(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'date_from': '2026-06-01', 'date_to': '2026-06-01'})
        assert resp.status_code == 200, resp.data
        return resp.data[0]['slots'][0]['appointments'][0]

    def test_incluye_plan_y_exp_date(self, admin_client, slot_cal, person, plans_subtype_a):
        Appointment.objects.create(person=person, slot=slot_cal)
        plan = self._plan(person, plans_subtype_a, 30, 5)
        appt = self._appt(admin_client)
        assert appt['plan_sub_type'] == {'id': plans_subtype_a.id, 'name': plans_subtype_a.name}
        assert appt['exp_date'] == plan.exp_date.isoformat()

    def test_sin_plan_null(self, admin_client, slot_cal, person):
        Appointment.objects.create(person=person, slot=slot_cal)
        appt = self._appt(admin_client)
        assert appt['plan_sub_type'] is None
        assert appt['exp_date'] is None

    def test_plan_sin_sesiones_null(self, admin_client, slot_cal, person, plans_subtype_a):
        Appointment.objects.create(person=person, slot=slot_cal)
        self._plan(person, plans_subtype_a, 30, 0)
        appt = self._appt(admin_client)
        assert appt['plan_sub_type'] is None
        assert appt['exp_date'] is None

    def test_plan_vencido_null(self, admin_client, slot_cal, person, plans_subtype_a):
        Appointment.objects.create(person=person, slot=slot_cal)
        self._plan(person, plans_subtype_a, -1, 5)
        appt = self._appt(admin_client)
        assert appt['plan_sub_type'] is None
        assert appt['exp_date'] is None

    def test_multi_plan_gana_exp_date_mas_lejano(self, admin_client, slot_cal, person, plans_subtype_a):
        Appointment.objects.create(person=person, slot=slot_cal)
        self._plan(person, plans_subtype_a, 10, 5)
        lejano = self._plan(person, plans_subtype_a, 60, 5)
        appt = self._appt(admin_client)
        assert appt['exp_date'] == lejano.exp_date.isoformat()


@pytest.mark.django_db
class TestCancel2HoursKAN171:
    """El límite de 2 hs aplica a estudiantes en AMBOS endpoints (POST /cancel/ y
    DELETE); el staff puede cancelar siempre; un alumno solo puede cancelar sus
    propios turnos."""

    def _slot(self, status, room, hours_ahead):
        from datetime import datetime
        dt = datetime.now() + timedelta(hours=hours_ahead)
        return Slot.objects.create(
            status=status, room=room, date=dt.date(),
            start_time=dt.time().replace(second=0, microsecond=0),
            end_time=(dt + timedelta(hours=1)).time().replace(second=0, microsecond=0),
            availability=10,
        )

    def _student(self, user_types, person, dni='45670010'):
        from apps.users.models import CustomUser
        u = CustomUser.objects.create_user(
            email=f'stud{dni}@test.com', password='p', name='S', last_name='O',
            dni=dni, tipo_usuario=user_types['student'],
        )
        u.person = person
        u.save(update_fields=['person'])
        return u

    def _client(self, user):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    @pytest.fixture(autouse=True)
    def _mock_action(self, monkeypatch):
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kwargs: None)

    # Estudiante: bloqueado <2h en AMBOS endpoints
    def test_student_delete_within_2h_returns_400(self, status, room, person, user_types):
        student = self._student(user_types, person)
        slot = self._slot(status, room, hours_ahead=1)
        appt = Appointment.objects.create(person=person, slot=slot)
        url = reverse('appointments-detail', args=[appt.pk])
        resp = self._client(student).delete(url, data={'code': student.code}, format='json')
        assert resp.status_code == 400
        appt.refresh_from_db()
        assert appt.deleted is None  # no se canceló
        slot.refresh_from_db()
        assert slot.availability == 10  # no se tocó el slot

    def test_student_cancel_within_2h_returns_400(self, status, room, person, user_types):
        student = self._student(user_types, person)
        slot = self._slot(status, room, hours_ahead=1)
        appt = Appointment.objects.create(person=person, slot=slot)
        url = reverse('appointments-cancel', args=[appt.pk])
        resp = self._client(student).post(url, data={'code': student.code}, format='json')
        assert resp.status_code == 400
        appt.refresh_from_db()
        assert appt.deleted is None
        slot.refresh_from_db()
        assert slot.availability == 10

    def test_student_no_evade_con_code_admin(self, status, room, person, user_types):
        # Evasión: un alumno autenticado que manda code='admin' sigue bloqueado <2h,
        # porque la ventana se evalúa sobre request.user, no sobre el code.
        student = self._student(user_types, person)
        slot = self._slot(status, room, hours_ahead=1)
        appt = Appointment.objects.create(person=person, slot=slot)
        url = reverse('appointments-detail', args=[appt.pk])
        resp = self._client(student).delete(url, data={'code': 'admin'}, format='json')
        assert resp.status_code == 400
        appt.refresh_from_db()
        assert appt.deleted is None

    # Estudiante: permitido ≥2h
    def test_student_delete_with_enough_time_ok(self, status, room, person, user_types):
        student = self._student(user_types, person)
        slot = self._slot(status, room, hours_ahead=3)
        appt = Appointment.objects.create(person=person, slot=slot)
        url = reverse('appointments-detail', args=[appt.pk])
        resp = self._client(student).delete(url, data={'code': student.code}, format='json')
        assert resp.status_code == 204
        appt.refresh_from_db()
        assert appt.deleted is not None

    def test_student_cancel_with_enough_time_ok(self, status, room, person, user_types):
        student = self._student(user_types, person)
        slot = self._slot(status, room, hours_ahead=3)
        appt = Appointment.objects.create(person=person, slot=slot)
        url = reverse('appointments-cancel', args=[appt.pk])
        resp = self._client(student).post(url, data={'code': student.code}, format='json')
        assert resp.status_code == 204

    # Staff: puede cancelar siempre (aún <2h)
    def test_staff_delete_within_2h_allowed(self, admin_client, status, room, person):
        slot = self._slot(status, room, hours_ahead=1)
        appt = Appointment.objects.create(person=person, slot=slot)
        url = reverse('appointments-detail', args=[appt.pk])
        resp = admin_client.delete(url, data={'code': 'admin'}, format='json')
        assert resp.status_code == 204

    def test_staff_cancel_within_2h_allowed(self, admin_client, status, room, person):
        slot = self._slot(status, room, hours_ahead=1)
        appt = Appointment.objects.create(person=person, slot=slot)
        url = reverse('appointments-cancel', args=[appt.pk])
        resp = admin_client.post(url, data={'code': 'admin'}, format='json')
        assert resp.status_code == 204

    # Estudiante no puede cancelar turno de otro
    def test_student_cannot_cancel_others_appointment(self, status, room, person, user_types, db):
        from apps.people.models import Person
        student = self._student(user_types, person)
        otro = Person.objects.create(name='Otro', last_name='X', dni='99990001')
        slot = self._slot(status, room, hours_ahead=3)
        appt_otro = Appointment.objects.create(person=otro, slot=slot)
        url = reverse('appointments-detail', args=[appt_otro.pk])
        resp = self._client(student).delete(url, data={'code': student.code}, format='json')
        assert resp.status_code == 404  # get_queryset lo scopea afuera
        appt_otro.refresh_from_db()
        assert appt_otro.deleted is None


@pytest.mark.django_db
class TestDeductSessionRaceKAN284:
    """La reserva descuenta la sesión de forma atómica: si otra reserva concurrente
    se llevó la última (find_consumable_plan devolvió un plan que ya está en 0), la
    reserva se rechaza sin crear turno ni tocar el slot."""

    def _plan_sin_sesiones(self, person, plans_subtype_a):
        return PersonActivePlan.objects.create(
            person=person, plans_subtype=plans_subtype_a,
            exp_date=date.today() + timedelta(days=30),
            sessions_total=1, sessions_remaining=0,
        )

    def test_create_race_sin_sesiones_devuelve_400(self, admin_client, slot_with_activity, person, plans_subtype_a, monkeypatch):
        plan = self._plan_sin_sesiones(person, plans_subtype_a)
        # Simula la carrera: el SELECT devuelve el plan, pero ya no tiene sesiones.
        monkeypatch.setattr('apps.appointments.views.find_consumable_plan', lambda p, s: plan)
        avail = slot_with_activity.availability
        resp = admin_client.post(reverse('appointments-list'),
                                 data={'slot_id': slot_with_activity.id, 'person_id': person.id, 'code': 'admin'},
                                 format='json')
        assert resp.status_code == 400
        assert 'sesiones' in resp.data['detail']
        assert not Appointment.objects.filter(slot=slot_with_activity, person=person).exists()
        slot_with_activity.refresh_from_db()
        assert slot_with_activity.availability == avail  # slot intacto

    def test_reserve_person_in_slot_race_sin_sesiones(self, person, slot_with_activity, plans_subtype_a, monkeypatch):
        from apps.slots.models import reserve_person_in_slot
        plan = self._plan_sin_sesiones(person, plans_subtype_a)
        monkeypatch.setattr('apps.people.selectors.find_consumable_plan', lambda p, s: plan)
        avail = slot_with_activity.availability
        estado = reserve_person_in_slot(person, slot_with_activity, None)
        assert estado == 'sin_sesiones'
        assert not Appointment.objects.filter(person=person, slot=slot_with_activity).exists()
        slot_with_activity.refresh_from_db()
        assert slot_with_activity.availability == avail

    def test_deduct_se_revierte_si_falla_la_reserva(self, person, slot_with_activity, plans_subtype_a, monkeypatch):
        # el descuento va dentro del atomic; si la creación del turno falla,
        # se revierte y sessions_remaining vuelve al valor original.
        from apps.slots.models import reserve_person_in_slot
        plan = PersonActivePlan.objects.create(
            person=person, plans_subtype=plans_subtype_a,
            exp_date=date.today() + timedelta(days=30), sessions_total=1, sessions_remaining=1,
        )
        monkeypatch.setattr('apps.people.selectors.find_consumable_plan', lambda p, s: plan)

        def boom(*a, **k):
            raise RuntimeError('boom')
        monkeypatch.setattr(Appointment.objects, 'create', boom)

        with pytest.raises(RuntimeError):
            reserve_person_in_slot(person, slot_with_activity, None)
        plan.refresh_from_db()
        assert plan.sessions_remaining == 1  # el descuento se revirtió


# filtro opcional por estudio en /appointments/

MSG_400 = "El parámetro 'studio' debe ser un número entero positivo."


@pytest.mark.django_db
class TestAppointmentsStudioFilterKAN146:
    URL = 'appointments-list'

    @pytest.fixture
    def data(self, person, slot, slot_b):
        from apps.people.models import Person
        otra = Person.objects.create(name='Otra', last_name='Alumna', dni='77777777')
        a1 = Appointment.objects.create(person=person, slot=slot)
        a2 = Appointment.objects.create(person=otra, slot=slot)
        b1 = Appointment.objects.create(person=person, slot=slot_b)
        return {'a': {a1.id, a2.id}, 'b': {b1.id}, 'otra': otra}

    def _ids(self, response):
        return {a['id'] for a in response.data}

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
        r = admin_client.get(reverse(self.URL) + f'?studio={studio.id}&studio={studio_b.id}')
        assert r.status_code == 200
        assert self._ids(r) == data['a'] | data['b']

    def test_combina_con_person_id(self, admin_client, data, studio, person):
        r = admin_client.get(reverse(self.URL), {'studio': studio.id, 'person_id': person.id})
        assert r.status_code == 200
        assert len(self._ids(r)) == 1 and self._ids(r) <= data['a']

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

    def test_usuario_con_permiso_200(self, consultor_client, data, studio):
        r = consultor_client.get(reverse(self.URL), {'studio': studio.id})
        assert r.status_code == 200
        assert self._ids(r) == data['a']

    def test_estudio_sin_datos_200_vacio(self, admin_client, data, empty_studio):
        r = admin_client.get(reverse(self.URL), {'studio': empty_studio.id})
        assert r.status_code == 200
        assert r.data == []

    def test_estudio_dado_de_baja_envuelve_respuesta(self, admin_client, person, status, deleted_studio):
        from apps.rooms.models import Room
        room = Room.all_objects.create(name='Sala vieja', studio=deleted_studio)
        sl = Slot.objects.create(status=status, room=room, date=date.today(),
                                 start_time=time(8, 0), end_time=time(9, 0), availability=5)
        ap = Appointment.objects.create(person=person, slot=sl)
        r = admin_client.get(reverse(self.URL), {'studio': deleted_studio.id})
        assert r.status_code == 200
        assert r.data['detail'] == f'El estudio con id {deleted_studio.id} está dado de baja.'
        assert [x['id'] for x in r.data['results']] == [ap.id]

    @pytest.mark.parametrize('value', ['abc', '999999', 'STUDIO_A'])
    def test_alumno_ignora_el_filtro(self, student_client, student_user, person, data, studio, value):
        # Alumnos: el parámetro se ignora (ni valida ni filtra); ven solo sus reservas.
        student_user.person = person
        student_user.save()
        value = str(studio.id) if value == 'STUDIO_A' else value
        r = student_client.get(reverse(self.URL) + f'?studio={value}')
        assert r.status_code == 200
        propias = {i for i in data['a'] | data['b']
                   if Appointment.objects.get(pk=i).person_id == person.id}
        assert self._ids(r) == propias
