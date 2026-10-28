import pytest
from datetime import time, date, timedelta, datetime
from dateutil.relativedelta import relativedelta
from django.urls import reverse
from .models import Slot, SlotTemplate, FixedSlot
from .serializer import FixedSlotSerializer
from .serializer import SlotSerializer, SlotTemplateSerializer
from apps.weeks.models import Week
from apps.teachers.models import Teacher
from apps.people.models import Person


# Helpers

def _next_weekday(weekday: int) -> date:
    """Retorna la próxima fecha (desde mañana) que caiga en el weekday dado (0=lunes)."""
    d = date.today() + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


@pytest.mark.django_db
class TestSlotSoftDelete:

    def test_delete_sets_deleted(self, status, room):
        slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=1),
            start_time=time(10, 0), end_time=time(11, 0), availability=10,
        )
        slot.delete()
        slot.refresh_from_db()
        assert slot.deleted is not None

    def test_objects_hides_deleted(self, status, room):
        slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=1),
            start_time=time(10, 0), end_time=time(11, 0), availability=10,
        )
        slot.delete()
        assert not Slot.objects.filter(pk=slot.pk).exists()

    def test_all_objects_includes_deleted(self, status, room):
        slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=1),
            start_time=time(10, 0), end_time=time(11, 0), availability=10,
        )
        slot.delete()
        assert Slot.all_objects.filter(pk=slot.pk).exists()

    def test_all_objects_dead_returns_deleted(self, status, room):
        slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=1),
            start_time=time(10, 0), end_time=time(11, 0), availability=10,
        )
        slot.delete()
        assert Slot.all_objects.dead().filter(pk=slot.pk).exists()

    def test_all_objects_alive_excludes_deleted(self, status, room):
        slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=1),
            start_time=time(10, 0), end_time=time(11, 0), availability=10,
        )
        slot.delete()
        assert not Slot.all_objects.alive().filter(pk=slot.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user, status, room):
        slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=1),
            start_time=time(10, 0), end_time=time(11, 0), availability=10,
        )
        slot.delete()
        qs = Slot.all_objects.for_user(admin_user)
        assert qs.filter(pk=slot.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user, status, room):
        slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=1),
            start_time=time(10, 0), end_time=time(11, 0), availability=10,
        )
        slot.delete()
        qs = Slot.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=slot.pk).exists()

    def test_restore(self, status, room):
        slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=1),
            start_time=time(10, 0), end_time=time(11, 0), availability=10,
        )
        slot.delete()
        slot.restore()
        slot.refresh_from_db()
        assert slot.deleted is None

    def test_hard_delete_removes_from_db(self, status, room):
        slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=1),
            start_time=time(10, 0), end_time=time(11, 0), availability=10,
        )
        pk = slot.pk
        slot.hard_delete()
        assert not Slot.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestSlotViewForUser:
    URL = 'slots-list'

    def test_admin_list_includes_deleted(self, admin_client, slot):
        slot.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert slot.id in ids

    def test_consultor_list_excludes_deleted(self, consultor_client, slot):
        slot.delete()
        response = consultor_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert slot.id not in ids

    def test_delete_endpoint_is_soft_delete(self, admin_client, slot):
        url = reverse('slots-detail', args=[slot.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert Slot.all_objects.filter(pk=slot.pk).exists()
        slot.refresh_from_db()
        assert slot.deleted is not None


# SlotTemplate.is_active
# Por qué: is_active controla si una plantilla puede usarse para generar slots.
# Se verifica que el default sea True, que se pueda desactivar, y que la API
# exponga el campo correctamente.

@pytest.mark.django_db
class TestSlotTemplateIsActive:

    def _make_template(self, week, room, activity_subtype=None):
        t = SlotTemplate.objects.create(
            start_time=time(9, 0),
            end_time=time(10, 0),
            room=room,
            availability=10,
            activity_subtype=activity_subtype,
        )
        t.days_of_week.set([week])
        return t

    def test_default_is_active_true(self, week, room):
        template = self._make_template(week, room)
        assert template.is_active is True

    def test_can_deactivate(self, week, room):
        template = self._make_template(week, room)
        template.is_active = False
        template.save()
        template.refresh_from_db()
        assert template.is_active is False

    def test_can_reactivate(self, week, room):
        template = self._make_template(week, room)
        template.is_active = False
        template.save()
        template.is_active = True
        template.save()
        template.refresh_from_db()
        assert template.is_active is True

    def test_api_list_includes_is_active(self, admin_client, week, room):
        self._make_template(week, room)
        response = admin_client.get(reverse('slottemplate-list'))
        assert response.status_code == 200
        assert len(response.data) > 0
        assert 'is_active' in response.data[0]

    def test_api_create_sets_is_active_true_by_default(self, admin_client, week, room):
        data = {
            'days_of_week_ids': [week.id],
            'start_time': '09:00:00',
            'end_time': '10:00:00',
            'room': room.id,
            'availability': 10,
        }
        response = admin_client.post(reverse('slottemplate-list'), data=data, format='json')
        assert response.status_code == 201
        assert response.data['is_active'] is True

    def test_api_patch_deactivates_template(self, admin_client, week, room):
        template = self._make_template(week, room)
        url = reverse('slottemplate-detail', args=[template.pk])
        response = admin_client.patch(url, data={'is_active': False}, format='json')
        assert response.status_code == 200
        template.refresh_from_db()
        assert template.is_active is False


# SlotGenerationViewSet
# Por qué: el generador tenía 3 problemas críticos:
# 1. Mapeaba weekday() + 1 -> Week.id asumiendo orden de inserción (frágil).
# 2. No requería ventana mínima de 3 meses -> slots se podían generar para mañana.
# 3. Check de duplicados era solo por template -> dos templates podían pisar el mismo slot.

@pytest.mark.django_db
class TestSlotGenerationWindowValidation:
    URL = 'generate-slots-list'

    @pytest.fixture
    def lunes(self, db):
        w, _ = Week.objects.get_or_create(day='Lunes')
        return w

    @pytest.fixture
    def template(self, lunes, room):
        t = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0),
            room=room, availability=10,
        )
        t.days_of_week.set([lunes])
        return t

    def test_date_to_below_3_months_returns_400(self, admin_client, template):
        today = date.today()
        response = admin_client.post(reverse(self.URL), data={
            'template_id': template.pk,
            'date_from': today.isoformat(),
            'date_to': (today + relativedelta(months=2)).isoformat(),
        }, format='json')
        assert response.status_code == 400
        assert '3' in response.data['detail']

    def test_date_to_exactly_3_months_is_accepted(self, admin_client, template):
        today = date.today()
        response = admin_client.post(reverse(self.URL), data={
            'template_id': template.pk,
            'date_from': today.isoformat(),
            'date_to': (today + relativedelta(months=3)).isoformat(),
        }, format='json')
        assert response.status_code == 201

    def test_date_to_more_than_3_months_is_accepted(self, admin_client, template):
        today = date.today()
        response = admin_client.post(reverse(self.URL), data={
            'template_id': template.pk,
            'date_from': today.isoformat(),
            'date_to': (today + relativedelta(months=4)).isoformat(),
        }, format='json')
        assert response.status_code == 201

    def test_inactive_template_returns_400(self, admin_client, template):
        template.is_active = False
        template.save()
        today = date.today()
        response = admin_client.post(reverse(self.URL), data={
            'template_id': template.pk,
            'date_from': today.isoformat(),
            'date_to': (today + relativedelta(months=3)).isoformat(),
        }, format='json')
        assert response.status_code == 400
        assert 'inactivo' in response.data['detail']

    def test_missing_fields_returns_400(self, admin_client):
        response = admin_client.post(reverse(self.URL), data={'template_id': 1}, format='json')
        assert response.status_code == 400


@pytest.mark.django_db
class TestSlotGenerationDayOfWeekMapping:
    """
    Verifica que la generación use el nombre del día (Week.day) y no el id.
    Un Week con id=99 y day='Lunes' debe generar slots en lunes correctamente.
    """
    URL = 'generate-slots-list'

    def test_generates_on_correct_weekday_regardless_of_week_id(self, admin_client, room):
        # Crear Week con id arbitrario alto para asegurar que el mapeo no depende del id
        lunes = Week.objects.create(id=50, day='Lunes')
        t = SlotTemplate.objects.create(
            start_time=time(10, 0), end_time=time(11, 0),
            room=room, availability=5,
        )
        t.days_of_week.set([lunes])

        today = date.today()
        response = admin_client.post(reverse(self.URL), data={
            'template_id': t.pk,
            'date_from': today.isoformat(),
            'date_to': (today + relativedelta(months=3)).isoformat(),
        }, format='json')
        assert response.status_code == 201

        # Todos los slots generados deben ser lunes (weekday() == 0)
        slots = Slot.objects.filter(template=t)
        assert slots.exists()
        for slot in slots:
            assert slot.date.weekday() == 0, f"{slot.date} no es lunes"

    def test_does_not_generate_on_wrong_day(self, admin_client, room):
        """Con template de solo Miércoles, no debe generarse ningún lunes."""
        miercoles = Week.objects.create(day='Miércoles')
        t = SlotTemplate.objects.create(
            start_time=time(14, 0), end_time=time(15, 0),
            room=room, availability=5,
        )
        t.days_of_week.set([miercoles])

        today = date.today()
        admin_client.post(reverse(self.URL), data={
            'template_id': t.pk,
            'date_from': today.isoformat(),
            'date_to': (today + relativedelta(months=3)).isoformat(),
        }, format='json')

        slots = Slot.objects.filter(template=t)
        for slot in slots:
            assert slot.date.weekday() == 2, f"{slot.date} no es miércoles"


@pytest.mark.django_db
class TestSlotGenerationCrossTemplateDuplicate:
    """
    Verifica que no se generen slots superpuestos entre templates distintos
    (misma fecha + hora + sala).
    """
    URL = 'generate-slots-list'

    def test_second_template_skips_existing_slot_same_room_time(self, admin_client, room):
        lunes = Week.objects.create(day='Lunes')
        next_monday = _next_weekday(0)

        # Template A genera un slot el próximo lunes
        t_a = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0),
            room=room, availability=10,
        )
        t_a.days_of_week.set([lunes])
        Slot.objects.create(
            template=t_a, date=next_monday,
            start_time=time(9, 0), end_time=time(10, 0),
            room=room, availability=10, status_id=1,
        )

        # Template B intenta generar en la misma sala/hora
        t_b = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0),
            room=room, availability=8,
        )
        t_b.days_of_week.set([lunes])

        today = date.today()
        response = admin_client.post(reverse(self.URL), data={
            'template_id': t_b.pk,
            'date_from': today.isoformat(),
            'date_to': (today + relativedelta(months=3)).isoformat(),
        }, format='json')

        assert response.status_code == 201
        # El slot del próximo lunes fue omitido (ya existía de template A)
        assert not Slot.objects.filter(template=t_b, date=next_monday).exists()


# SlotsViewSet.create — validaciones
# Por qué: la creación manual no validaba el día de semana contra el template
# ni detectaba duplicados cross-template por sala.

@pytest.mark.django_db
class TestSlotCreateValidation:
    URL = 'slots-list'

    @pytest.fixture
    def lunes(self, db):
        w, _ = Week.objects.get_or_create(day='Lunes')
        return w

    @pytest.fixture
    def template_lunes(self, lunes, room):
        t = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0),
            room=room, availability=10,
        )
        t.days_of_week.set([lunes])
        return t

    def test_manual_create_on_wrong_weekday_returns_400(self, admin_client, template_lunes, status):
        """Crear un slot en martes con template de lunes debe fallar."""
        next_tuesday = _next_weekday(1)
        response = admin_client.post(reverse(self.URL), data={
            'date': next_tuesday.isoformat(),
            'start_time': '09:00:00',
            'end_time': '10:00:00',
            'status_id': status.id,
            'room': template_lunes.room.id,
            'availability': 10,
            'template': template_lunes.pk,
        }, format='json')
        assert response.status_code == 400
        assert 'template' in response.data['detail'].lower() or 'día' in response.data['detail'].lower()

    def test_manual_create_on_correct_weekday_succeeds(self, admin_client, template_lunes, status):
        """Crear un slot en lunes con template de lunes debe funcionar."""
        next_monday = _next_weekday(0)
        response = admin_client.post(reverse(self.URL), data={
            'date': next_monday.isoformat(),
            'start_time': '09:00:00',
            'end_time': '10:00:00',
            'status_id': status.id,
            'room': template_lunes.room.id,
            'availability': 10,
            'template': template_lunes.pk,
        }, format='json')
        assert response.status_code == 201

    def test_duplicate_date_time_room_returns_400(self, admin_client, slot, status):
        """Crear un slot con misma fecha+hora+sala que uno existente debe fallar."""
        response = admin_client.post(reverse(self.URL), data={
            'date': slot.date.isoformat(),
            'start_time': slot.start_time.strftime('%H:%M:%S'),
            'end_time': slot.end_time.strftime('%H:%M:%S'),
            'status_id': status.id,
            'room': slot.room.id,
            'availability': 5,
        }, format='json')
        assert response.status_code == 400

    def test_inactive_template_returns_400(self, admin_client, template_lunes, status):
        """Crear slot con template inactivo debe fallar."""
        template_lunes.is_active = False
        template_lunes.save()
        next_monday = _next_weekday(0)
        response = admin_client.post(reverse(self.URL), data={
            'date': next_monday.isoformat(),
            'start_time': '09:00:00',
            'end_time': '10:00:00',
            'status_id': status.id,
            'room': template_lunes.room.id,
            'availability': 10,
            'template': template_lunes.pk,
        }, format='json')
        assert response.status_code == 400
        assert 'inactivo' in response.data['detail']


# turnos fijos generan reservas (Appointment)
@pytest.mark.django_db
class TestFixedSlotReservations:
    """Crear un turno fijo materializa reservas (Appointment) en los slots del template."""

    URL = 'fixed-slots-list'
    GEN_URL = 'generate-slots-list'

    @pytest.fixture
    def lunes(self, db):
        w, _ = Week.objects.get_or_create(day='Lunes')
        return w

    @pytest.fixture
    def template(self, lunes, room):
        t = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0),
            room=room, availability=10,
        )
        t.days_of_week.set([lunes])
        return t

    @pytest.fixture(autouse=True)
    def _mock_action_audit(self, monkeypatch):
        """Action usa ArrayField (Postgres): no se puede persistir en sqlite (tests).
        Se mockea el audit log por default; el test que verifica el audit
        sobreescribe este mock con su propia captura."""
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kw: None)

    def _slot(self, template, status, room, d, availability=10, status_id=1):
        return Slot.objects.create(
            template=template, date=d,
            start_time=template.start_time, end_time=template.end_time,
            room=room, availability=availability, status_id=status_id,
        )

    # Retroactivo
    def test_crear_turno_fijo_reserva_slots_existentes(
        self, admin_client, template, status, room, person
    ):
        from apps.appointments.models import Appointment
        monday1 = _next_weekday(0)
        monday2 = monday1 + timedelta(days=7)
        s1 = self._slot(template, status, room, monday1)
        s2 = self._slot(template, status, room, monday2)

        response = admin_client.post(reverse(self.URL), data={
            'person': person.id, 'template_id': template.id,
            'start_date': date.today().isoformat(),
            'end_date': (date.today() + timedelta(days=60)).isoformat(),
        }, format='json')

        assert response.status_code == 201
        assert response.data['reservas_creadas'] == 2
        assert Appointment.objects.filter(person=person, slot__template=template).count() == 2
        s1.refresh_from_db(); s2.refresh_from_db()
        assert s1.availability == 9
        assert s2.availability == 9

    # Forward (al generar slots nuevos)
    def test_generar_slots_reserva_turnos_fijos_activos(
        self, admin_client, template, status, room, person
    ):
        from apps.appointments.models import Appointment
        # Turno fijo abierto (sin end_date) creado antes de existir slots
        resp = admin_client.post(reverse(self.URL), data={
            'person': person.id, 'template_id': template.id,
            'start_date': date.today().isoformat(),
        }, format='json')
        assert resp.status_code == 201
        assert resp.data['reservas_creadas'] == 0

        today = date.today()
        gen = admin_client.post(reverse(self.GEN_URL), data={
            'template_id': template.id,
            'date_from': today.isoformat(),
            'date_to': (today + relativedelta(months=3)).isoformat(),
        }, format='json')
        assert gen.status_code == 201

        slots = Slot.objects.filter(template=template)
        assert slots.exists()
        for s in slots:
            assert Appointment.objects.filter(person=person, slot=s).exists(), \
                f"slot {s.date} sin reserva del turno fijo"
            assert s.availability == 9

    # Idempotencia
    def test_no_duplica_reserva_existente(
        self, admin_client, template, status, room, person
    ):
        from apps.appointments.models import Appointment
        monday = _next_weekday(0)
        s = self._slot(template, status, room, monday)
        Appointment.objects.create(person=person, slot=s, reserved=False)

        response = admin_client.post(reverse(self.URL), data={
            'person': person.id, 'template_id': template.id,
            'start_date': date.today().isoformat(),
            'end_date': (date.today() + timedelta(days=60)).isoformat(),
        }, format='json')
        assert response.status_code == 201
        assert response.data['reservas_creadas'] == 0
        assert Appointment.objects.filter(person=person, slot=s).count() == 1

    # Slot lleno se saltea
    def test_slot_lleno_se_saltea(
        self, admin_client, template, status, room, person
    ):
        from apps.status.models import Status
        from apps.appointments.models import Appointment
        Status.objects.get_or_create(id=2, defaults={'status': 'Lleno'})
        monday = _next_weekday(0)
        s = self._slot(template, status, room, monday, availability=0, status_id=2)

        response = admin_client.post(reverse(self.URL), data={
            'person': person.id, 'template_id': template.id,
            'start_date': date.today().isoformat(),
            'end_date': (date.today() + timedelta(days=60)).isoformat(),
        }, format='json')
        assert response.status_code == 201
        assert response.data['reservas_creadas'] == 0
        assert not Appointment.objects.filter(person=person, slot=s).exists()

    # Fuera de rango no reserva
    def test_slot_fuera_de_rango_no_reserva(
        self, admin_client, template, status, room, person
    ):
        from apps.appointments.models import Appointment
        far_monday = _next_weekday(0) + timedelta(days=70)
        s = self._slot(template, status, room, far_monday)

        response = admin_client.post(reverse(self.URL), data={
            'person': person.id, 'template_id': template.id,
            'start_date': date.today().isoformat(),
            'end_date': (date.today() + timedelta(days=60)).isoformat(),
        }, format='json')
        assert response.status_code == 201
        assert response.data['reservas_creadas'] == 0
        assert not Appointment.objects.filter(person=person, slot=s).exists()

    def test_reserva_automatica_setea_fixed_slot_y_reserved(
        self, admin_client, template, status, room, person
    ):
        from apps.appointments.models import Appointment
        s = self._slot(template, status, room, _next_weekday(0))
        resp = admin_client.post(reverse(self.URL), data={
            'person': person.id, 'template_id': template.id,
            'start_date': date.today().isoformat(),
        }, format='json')
        assert resp.status_code == 201
        appt = Appointment.objects.get(person=person, slot=s)
        assert appt.reserved is False
        assert appt.fixed_slot_id == resp.data['id']

    def test_slot_lleno_genera_warning_no_falla(
        self, admin_client, template, status, room, person
    ):
        # slot lleno (availability=0, status LLENO) => se saltea con warning
        from apps.status.models import Status
        Status.objects.get_or_create(id=2, defaults={'status': 'Lleno'})
        d = _next_weekday(0)
        s = self._slot(template, status, room, d, availability=0, status_id=2)
        resp = admin_client.post(reverse(self.URL), data={
            'person': person.id, 'template_id': template.id,
            'start_date': date.today().isoformat(),
        }, format='json')
        assert resp.status_code == 201
        assert resp.data['reservas_creadas'] == 0
        reasons = [w['reason'] for w in resp.data['warnings']]
        assert 'slot_lleno' in reasons
        w = next(w for w in resp.data['warnings'] if w['reason'] == 'slot_lleno')
        assert w['slot'] == s.id
        assert w['date'] == d.isoformat()

    def test_sin_plan_activo_genera_warning_no_bloquea(
        self, admin_client, template, status, room, person
    ):
        self._slot(template, status, room, _next_weekday(0))
        resp = admin_client.post(reverse(self.URL), data={
            'person': person.id, 'template_id': template.id,
            'start_date': date.today().isoformat(),
        }, format='json')
        assert resp.status_code == 201           # no bloquea
        reasons = [w['reason'] for w in resp.data['warnings']]
        assert 'sin_plan_activo' in reasons

    def test_con_plan_activo_no_genera_warning_de_plan(
        self, admin_client, template, status, room, person, person_active_plan
    ):
        self._slot(template, status, room, _next_weekday(0))
        resp = admin_client.post(reverse(self.URL), data={
            'person': person.id, 'template_id': template.id,
            'start_date': date.today().isoformat(),
        }, format='json')
        assert resp.status_code == 201
        reasons = [w['reason'] for w in resp.data['warnings']]
        assert 'sin_plan_activo' not in reasons

    def test_alta_registra_action_audit(
        self, admin_client, template, status, room, person, monkeypatch
    ):
        from apps.actions.models import Action
        capturados = []
        monkeypatch.setattr(Action.objects, "create", lambda **kw: capturados.append(kw))

        self._slot(template, status, room, _next_weekday(0))
        resp = admin_client.post(reverse(self.URL), data={
            'person': person.id, 'template_id': template.id,
            'start_date': date.today().isoformat(),
        }, format='json')
        assert resp.status_code == 201
        assert len(capturados) == 1
        kw = capturados[0]
        assert kw['action'] == 'Crear'
        assert kw['target'] == 'Turno fijo'
        assert kw['target_id'] == resp.data['id']

    # Serializer reservas_count (visualización)
    def test_serializer_expone_reservas_count(
        self, admin_client, template, status, room, person
    ):
        monday1 = _next_weekday(0)
        monday2 = monday1 + timedelta(days=7)
        self._slot(template, status, room, monday1)
        self._slot(template, status, room, monday2)
        create = admin_client.post(reverse(self.URL), data={
            'person': person.id, 'template_id': template.id,
            'start_date': date.today().isoformat(),
            'end_date': (date.today() + timedelta(days=60)).isoformat(),
        }, format='json')
        fixed_id = create.data['id']
        detail = admin_client.get(reverse('fixed-slots-detail', args=[fixed_id]))
        assert detail.status_code == 200
        assert detail.data['reservas_count'] == 2


# generate-slots: audit + warnings de reservas forward
# Por qué: el loop forward de SlotGenerationViewSet.create descartaba el estado
# devuelto por reserve_person_in_slot ("creado"/"slot_lleno"/"ya_reservado").
# Ahora se cuenta, se loguean warnings y se registra UN Action-resumen por corrida.

@pytest.mark.django_db
class TestGenerateSlotsForwardAuditYWarnings:
    GEN_URL = 'generate-slots-list'

    @pytest.fixture
    def lunes(self, db):
        w, _ = Week.objects.get_or_create(day='Lunes')
        return w

    @pytest.fixture
    def template(self, lunes, room):
        t = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0),
            room=room, availability=10,
        )
        t.days_of_week.set([lunes])
        return t

    def test_reservas_forward_registran_un_action_resumen(
        self, admin_client, template, person, monkeypatch
    ):
        from apps.actions.models import Action
        capturados = []
        monkeypatch.setattr(Action.objects, "create", lambda **kw: capturados.append(kw))

        FixedSlot.objects.create(person=person, template=template, start_date=date.today())

        today = date.today()
        resp = admin_client.post(reverse(self.GEN_URL), data={
            'template_id': template.id,
            'date_from': today.isoformat(),
            'date_to': (today + relativedelta(months=3)).isoformat(),
        }, format='json')

        assert resp.status_code == 201
        assert resp.data['reservas_automaticas'] > 0
        assert len(capturados) == 1
        kw = capturados[0]
        assert kw['target'] == "Reservas automáticas (generación)"
        assert kw['target_id'] == template.id
        assert kw['action'] == 'Crear'

    def test_slot_lleno_genera_warnings_forward_sin_action(
        self, admin_client, template, person, monkeypatch
    ):
        from apps.actions.models import Action
        capturados = []
        monkeypatch.setattr(Action.objects, "create", lambda **kw: capturados.append(kw))

        template.availability = 0
        template.save()

        FixedSlot.objects.create(person=person, template=template, start_date=date.today())

        today = date.today()
        resp = admin_client.post(reverse(self.GEN_URL), data={
            'template_id': template.id,
            'date_from': today.isoformat(),
            'date_to': (today + relativedelta(months=3)).isoformat(),
        }, format='json')

        assert resp.status_code == 201
        assert resp.data['reservas_automaticas'] == 0
        reasons = [w['reason'] for w in resp.data['warnings']]
        assert 'slot_lleno' in reasons
        assert len(capturados) == 0


@pytest.mark.django_db
class TestReservePersonInSlot:
    """Unit del helper reserve_person_in_slot."""

    @pytest.fixture
    def template(self, week, room):
        t = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0),
            room=room, availability=10,
        )
        t.days_of_week.set([week])
        return t

    def test_reserva_decrementa_y_marca_lleno(self, status, room, person, template):
        from apps.status.models import Status
        from apps.slots.models import reserve_person_in_slot
        from apps.appointments.models import Appointment
        Status.objects.get_or_create(id=2, defaults={'status': 'Lleno'})
        s = Slot.objects.create(
            status=status, room=room, date=date.today() + timedelta(days=1),
            start_time=time(9, 0), end_time=time(10, 0), availability=1,
        )
        fs = FixedSlot.objects.create(person=person, template=template, start_date=date.today())
        estado = reserve_person_in_slot(person, s, fs)
        s.refresh_from_db()
        assert estado == "creado"
        assert Appointment.objects.filter(person=person, slot=s).count() == 1
        assert s.availability == 0
        assert s.status_id == 2

    def test_reserva_duplicada_devuelve_false(self, status, room, person, template):
        from apps.slots.models import reserve_person_in_slot
        from apps.appointments.models import Appointment
        s = Slot.objects.create(
            status=status, room=room, date=date.today() + timedelta(days=1),
            start_time=time(9, 0), end_time=time(10, 0), availability=5,
        )
        fs = FixedSlot.objects.create(person=person, template=template, start_date=date.today())
        assert reserve_person_in_slot(person, s, fs) == "creado"
        assert reserve_person_in_slot(person, s, fs) == "ya_reservado"
        assert Appointment.objects.filter(person=person, slot=s).count() == 1
        appt = Appointment.objects.get(person=person, slot=s)
        assert appt.reserved is False
        assert appt.fixed_slot == fs


@pytest.mark.django_db
class TestFixedSlotDateValidation:
    """end_date debe ser posterior o igual a start_date (end_date es opcional)."""

    def _template(self, week, room):
        t = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0), room=room, availability=10,
        )
        t.days_of_week.set([week])
        return t

    def test_rejects_end_before_start(self, person, week, room):
        t = self._template(week, room)
        s = FixedSlotSerializer(data={
            'person': person.id, 'template_id': t.id,
            'start_date': '2026-06-10', 'end_date': '2026-06-05',
        })
        assert not s.is_valid()
        assert 'end_date' in s.errors

    def test_accepts_end_after_start(self, person, week, room):
        t = self._template(week, room)
        s = FixedSlotSerializer(data={
            'person': person.id, 'template_id': t.id,
            'start_date': '2026-06-10', 'end_date': '2026-06-20',
        })
        assert s.is_valid(), s.errors

    def test_accepts_equal_dates(self, person, week, room):
        t = self._template(week, room)
        s = FixedSlotSerializer(data={
            'person': person.id, 'template_id': t.id,
            'start_date': '2026-06-10', 'end_date': '2026-06-10',
        })
        assert s.is_valid(), s.errors

    def test_accepts_no_end_date(self, person, week, room):
        t = self._template(week, room)
        s = FixedSlotSerializer(data={
            'person': person.id, 'template_id': t.id,
            'start_date': '2026-06-10',
        })
        assert s.is_valid(), s.errors


# Soft-delete cascade: SlotTemplate -> FixedSlot
# Por qué: al eliminar suavemente un SlotTemplate, sus turnos fijos activos
# deben quedar también eliminados suavemente para mantener integridad.

@pytest.mark.django_db
class TestSlotTemplateFixedSlotCascade:
    """Soft-delete de SlotTemplate propaga el soft-delete a sus FixedSlot activos."""

    def _template(self, week, room, start=time(9, 0), end=time(10, 0)):
        t = SlotTemplate.objects.create(
            start_time=start, end_time=end, room=room, availability=10,
        )
        t.days_of_week.set([week])
        return t

    def test_soft_delete_cascades_a_fixed_slots(self, person, week, room):
        """Soft-delete de SlotTemplate setea deleted en sus FixedSlot activos."""
        t = self._template(week, room)
        fs = FixedSlot.objects.create(person=person, template=t, start_date=date.today())
        t.delete()
        fs.refresh_from_db()
        assert fs.deleted is not None

    def test_fixed_slots_ocultos_tras_soft_delete_template(self, person, week, room):
        """Tras soft-delete de SlotTemplate, sus FixedSlot desaparecen de FixedSlot.objects."""
        t = self._template(week, room)
        fs = FixedSlot.objects.create(person=person, template=t, start_date=date.today())
        t.delete()
        assert not FixedSlot.objects.filter(pk=fs.pk).exists()

    def test_no_afecta_fixed_slots_de_otro_template(self, person, week, room):
        """Soft-delete de un SlotTemplate no afecta los FixedSlot de otro template."""
        person_b = Person.objects.create(name='Ana', last_name='Lopez', dni='11111111')
        t_a = self._template(week, room, start=time(9, 0), end=time(10, 0))
        t_b = self._template(week, room, start=time(11, 0), end=time(12, 0))
        FixedSlot.objects.create(person=person, template=t_a, start_date=date.today())
        fs_b = FixedSlot.objects.create(person=person_b, template=t_b, start_date=date.today())
        t_a.delete()
        assert FixedSlot.objects.filter(pk=fs_b.pk).exists()
        fs_b.refresh_from_db()
        assert fs_b.deleted is None

    def test_no_re_borra_fixed_slot_ya_eliminado(self, person, week, room):
        """Un FixedSlot ya soft-deleted mantiene su fecha deleted original tras el cascade."""
        t = self._template(week, room)
        fs = FixedSlot.objects.create(person=person, template=t, start_date=date.today())
        original_deleted = date(2026, 1, 1)
        FixedSlot.all_objects.filter(pk=fs.pk).update(deleted=original_deleted)
        t.delete()
        fs.refresh_from_db()
        assert fs.deleted == original_deleted


# Validación de solapamiento de turnos fijos
# Por qué: unique_together(person, template) previene duplicar el MISMO template
# pero no detecta dos templates DISTINTOS que caigan el mismo día y horario.

@pytest.mark.django_db
class TestFixedSlotOverlapValidation:
    """FixedSlotSerializer rechaza turnos fijos que se pisan en día + horario."""

    def _template(self, room, start_time, end_time, days):
        t = SlotTemplate.objects.create(
            start_time=start_time, end_time=end_time, room=room, availability=10,
        )
        t.days_of_week.set(days)
        return t

    def _crear_fixed_slot(self, person, template, start_date='2026-01-01', end_date=None):
        kwargs = {'person': person, 'template': template, 'start_date': start_date}
        if end_date:
            kwargs['end_date'] = end_date
        return FixedSlot.objects.create(**kwargs)

    def test_rechaza_mismo_dia_misma_hora(self, person, week, room):
        """Misma persona, template distinto, mismo día y misma hora -> rechazado."""
        t_existente = self._template(room, time(9, 0), time(10, 0), [week])
        self._crear_fixed_slot(person, t_existente)

        t_nuevo = self._template(room, time(9, 0), time(10, 0), [week])
        s = FixedSlotSerializer(data={
            'person': person.id, 'template_id': t_nuevo.id,
            'start_date': '2026-06-10',
        })
        assert not s.is_valid()

    def test_rechaza_horario_parcialmente_solapado(self, person, week, room):
        """Mismo día, horarios que se solapan parcialmente -> rechazado."""
        t_existente = self._template(room, time(9, 0), time(10, 30), [week])
        self._crear_fixed_slot(person, t_existente)

        t_nuevo = self._template(room, time(10, 0), time(11, 0), [week])
        s = FixedSlotSerializer(data={
            'person': person.id, 'template_id': t_nuevo.id,
            'start_date': '2026-06-10',
        })
        assert not s.is_valid()

    def test_acepta_misma_hora_dia_distinto(self, person, week, room):
        """Misma hora pero día de semana distinto -> aceptado (sin solapamiento de día)."""
        martes = Week.objects.create(day='Martes')
        t_existente = self._template(room, time(9, 0), time(10, 0), [week])  # Lunes
        self._crear_fixed_slot(person, t_existente)

        t_nuevo = self._template(room, time(9, 0), time(10, 0), [martes])  # Martes
        s = FixedSlotSerializer(data={
            'person': person.id, 'template_id': t_nuevo.id,
            'start_date': '2026-06-10',
        })
        assert s.is_valid(), s.errors

    def test_acepta_mismo_dia_horarios_sin_solapamiento(self, person, week, room):
        """Mismo día pero horarios que NO se solapan (9-10 vs 10-11) -> aceptado."""
        t_existente = self._template(room, time(9, 0), time(10, 0), [week])
        self._crear_fixed_slot(person, t_existente)

        t_nuevo = self._template(room, time(10, 0), time(11, 0), [week])
        s = FixedSlotSerializer(data={
            'person': person.id, 'template_id': t_nuevo.id,
            'start_date': '2026-06-10',
        })
        assert s.is_valid(), s.errors

    def test_acepta_mismo_dia_hora_periodos_fecha_sin_solapamiento(self, person, week, room):
        """Mismo día y hora pero períodos de fecha que no se solapan -> aceptado."""
        t_existente = self._template(room, time(9, 0), time(10, 0), [week])
        # El existente termina antes de que empiece el nuevo
        self._crear_fixed_slot(person, t_existente, start_date='2026-01-01', end_date='2026-03-31')

        t_nuevo = self._template(room, time(9, 0), time(10, 0), [week])
        s = FixedSlotSerializer(data={
            'person': person.id, 'template_id': t_nuevo.id,
            'start_date': '2026-04-01',
        })
        assert s.is_valid(), s.errors

    def test_ignora_fixed_slots_soft_deleted(self, person, week, room):
        """FixedSlots soft-deleted no se consideran para el chequeo de solapamiento."""
        t_existente = self._template(room, time(9, 0), time(10, 0), [week])
        fs = self._crear_fixed_slot(person, t_existente)
        fs.delete()  # soft-delete del existente

        # Template distinto para evitar unique_together con el registro ya en DB
        t_nuevo = self._template(room, time(9, 0), time(10, 0), [week])
        s = FixedSlotSerializer(data={
            'person': person.id, 'template_id': t_nuevo.id,
            'start_date': '2026-06-10',
        })
        assert s.is_valid(), s.errors

    def test_update_no_choca_consigo_mismo(self, person, week, room):
        """En update (PATCH), el FixedSlot no se compara consigo mismo -> sin falso positivo."""
        t = self._template(room, time(9, 0), time(10, 0), [week])
        fs = self._crear_fixed_slot(person, t, start_date='2026-06-01')

        # PATCH cambiando solo start_date -> no debe reportar solapamiento consigo mismo
        s = FixedSlotSerializer(instance=fs, data={'start_date': '2026-06-10'}, partial=True)
        assert s.is_valid(), s.errors


@pytest.mark.django_db
class TestFixedSlotRestoreOnRecreate:
    """Recrear un (person, template) soft-deleted reutiliza la misma fila."""

    def _template(self, room, start_time=time(9, 0), end_time=time(10, 0), days=None, week=None):
        t = SlotTemplate.objects.create(
            start_time=start_time, end_time=end_time, room=room, availability=10,
        )
        t.days_of_week.set(days if days is not None else [week])
        return t

    def _save(self, data):
        s = FixedSlotSerializer(data=data)
        assert s.is_valid(), s.errors
        return s.save()

    def test_recrear_soft_deleted_reutiliza_misma_fila(self, person, week, room):
        t = self._template(room, week=week)
        fs = FixedSlot.objects.create(person=person, template=t, start_date=date(2026, 1, 1))
        fs.delete()  # soft-delete
        assert fs.deleted is not None

        obj = self._save({
            'person': person.id, 'template_id': t.id, 'start_date': '2026-05-01',
        })

        assert obj.pk == fs.pk                       # misma fila
        assert obj.deleted is None                   # restaurada
        assert obj.start_date == date(2026, 5, 1)    # datos nuevos
        assert FixedSlot.all_objects.filter(person=person, template=t).count() == 1

    def test_restore_actualiza_end_date_y_observation(self, person, week, room):
        t = self._template(room, week=week)
        fs = FixedSlot.objects.create(
            person=person, template=t, start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 1), observation='vieja',
        )
        fs.delete()

        obj = self._save({
            'person': person.id, 'template_id': t.id,
            'start_date': '2026-05-01', 'end_date': '2026-06-01', 'observation': 'nueva',
        })

        assert obj.pk == fs.pk
        assert obj.end_date == date(2026, 6, 1)
        assert obj.observation == 'nueva'

    def test_restore_sin_end_date_queda_abierto(self, person, week, room):
        t = self._template(room, week=week)
        fs = FixedSlot.objects.create(
            person=person, template=t, start_date=date(2026, 1, 1), end_date=date(2026, 3, 1),
        )
        fs.delete()

        obj = self._save({
            'person': person.id, 'template_id': t.id, 'start_date': '2026-05-01',
        })

        assert obj.pk == fs.pk
        assert obj.end_date is None                  # semántica de alta: sin end_date = abierto

    def test_alta_sin_baja_previa_crea_fila_nueva(self, person, week, room):
        t = self._template(room, week=week)

        obj = self._save({
            'person': person.id, 'template_id': t.id, 'start_date': '2026-05-01',
        })

        assert obj.pk is not None
        assert obj.deleted is None
        assert FixedSlot.all_objects.filter(person=person, template=t).count() == 1

    def test_duplicado_activo_devuelve_400(self, person, week, room):
        # Regresión: el UniqueTogetherValidator de DRF corta el alta sobre un par activo.
        t = self._template(room, week=week)
        FixedSlot.objects.create(person=person, template=t, start_date=date(2026, 1, 1))

        s = FixedSlotSerializer(data={
            'person': person.id, 'template_id': t.id, 'start_date': '2026-05-01',
        })
        assert not s.is_valid()

    def test_restore_respeta_solapamiento_no_restaura(self, person, week, room):
        # La baja es del template A; hay un turno ACTIVO en template B que se pisa (mismo día/hora).
        t_a = self._template(room, time(13, 0), time(14, 0), week=week)
        fs_a = FixedSlot.objects.create(person=person, template=t_a, start_date=date(2026, 1, 1))
        fs_a.delete()

        t_b = self._template(room, time(13, 30), time(14, 30), week=week)
        FixedSlot.objects.create(person=person, template=t_b, start_date=date(2026, 1, 1))

        s = FixedSlotSerializer(data={
            'person': person.id, 'template_id': t_a.id, 'start_date': '2026-05-01',
        })
        assert not s.is_valid()                      # solapa con el activo de t_b
        fs_a.refresh_from_db()
        assert fs_a.deleted is not None              # la baja NO se restauró

    def test_recrear_tras_cascade_de_persona(self, person, week, room):
        # Flujo real (baja por falta de pago y reactivación):
        # person.delete() hace soft-delete en cascada del FixedSlot; se reactiva la
        # persona (person.restore(), que NO restaura el FixedSlot); recrear el turno
        # reutiliza la fila. Nota: el campo `person` del serializer valida contra
        # Person.objects (solo activos), por eso hay que restaurar la persona primero.
        t = self._template(room, week=week)
        fs = FixedSlot.objects.create(person=person, template=t, start_date=date(2026, 1, 1))
        person.delete()
        fs.refresh_from_db()
        assert fs.deleted is not None                # cascade lo bajó
        person.restore()                             # reactivar persona (FS sigue soft-deleted)
        fs.refresh_from_db()
        assert fs.deleted is not None

        obj = self._save({
            'person': person.id, 'template_id': t.id, 'start_date': '2026-05-01',
        })
        assert obj.pk == fs.pk
        assert obj.deleted is None

    def test_recrear_via_http_restaura_misma_fila(self, admin_client, person, week, room, monkeypatch):
        """End-to-end por HTTP: POST /fixed-slots/ sobre un (person, template)
        soft-deleted devuelve 201 y reutiliza la misma fila (no inserta otra)."""
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kw: None)
        t = self._template(room, week=week)
        fs = FixedSlot.objects.create(person=person, template=t, start_date=date(2026, 1, 1))
        fs.delete()

        resp = admin_client.post(reverse('fixed-slots-list'), data={
            'person': person.id, 'template_id': t.id, 'start_date': '2026-05-01',
        }, format='json')

        assert resp.status_code == 201, resp.data
        assert resp.data['id'] == fs.pk              # reutilizó la misma fila
        fs.refresh_from_db()
        assert fs.deleted is None
        assert FixedSlot.all_objects.filter(person=person, template=t).count() == 1


@pytest.mark.django_db
class TestSlotTimeValidation:
    """end_time debe ser posterior a start_time, tanto en Slot como en SlotTemplate."""

    def test_slot_rejects_end_before_start(self):
        s = SlotSerializer(data={'start_time': '11:00:00', 'end_time': '10:00:00'})
        assert not s.is_valid()
        assert 'end_time' in s.errors

    def test_slot_rejects_end_equal_start(self):
        s = SlotSerializer(data={'start_time': '10:00:00', 'end_time': '10:00:00'})
        assert not s.is_valid()
        assert 'end_time' in s.errors

    def test_slot_accepts_end_after_start(self):
        s = SlotSerializer(data={'start_time': '09:00:00', 'end_time': '10:00:00'})
        assert s.is_valid(), s.errors

    def test_slottemplate_rejects_end_before_start(self, week, room):
        s = SlotTemplateSerializer(data={
            'days_of_week_ids': [week.id],
            'start_time': '11:00:00', 'end_time': '10:00:00',
            'room': room.id, 'availability': 10,
        })
        assert not s.is_valid()
        assert 'end_time' in s.errors

    def test_slottemplate_accepts_end_after_start(self, week, room):
        s = SlotTemplateSerializer(data={
            'days_of_week_ids': [week.id],
            'start_time': '09:00:00', 'end_time': '10:00:00',
            'room': room.id, 'availability': 10,
        })
        assert s.is_valid(), s.errors


@pytest.mark.django_db
class TestSoftDeleteMixinCoercion:
    """
    El valor escrito por delete() debe coincidir con el tipo del campo:
    DateField -> date (no datetime), DateTimeField -> datetime.
    Verifica el valor en memoria inmediatamente despues de delete(),
    antes de que la DB coaccione el tipo.
    """

    def test_datefield_delete_stores_date_not_datetime(self, status, room):
        slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=1),
            start_time=time(10, 0), end_time=time(11, 0), availability=10,
        )
        slot.delete()
        assert isinstance(slot.deleted, date)
        assert not isinstance(slot.deleted, datetime)

    def test_datetimefield_delete_stores_datetime(self):
        teacher = Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        teacher.delete()
        assert isinstance(teacher.deleted, datetime)

    def test_restore_clears_deleted(self, status, room):
        slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=1),
            start_time=time(10, 0), end_time=time(11, 0), availability=10,
        )
        slot.delete()
        slot.restore()
        assert slot.deleted is None
        assert Slot.objects.filter(pk=slot.pk).exists()

    def test_hard_delete_removes_row(self, status, room):
        slot = Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=1),
            start_time=time(10, 0), end_time=time(11, 0), availability=10,
        )
        pk = slot.pk
        slot.hard_delete()
        assert not Slot.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestFixedSlotBajaCancelaReservas:
    URL = 'fixed-slots-list'

    @pytest.fixture
    def lunes(self, db):
        w, _ = Week.objects.get_or_create(day='Lunes')
        return w

    @pytest.fixture
    def template(self, lunes, room):
        t = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0), room=room, availability=10,
        )
        t.days_of_week.set([lunes])
        return t

    def _slot(self, template, status, room, d, availability=10, status_id=1):
        return Slot.objects.create(
            template=template, date=d, start_time=template.start_time,
            end_time=template.end_time, room=room, availability=availability, status_id=status_id,
        )

    def test_baja_cancela_futuras_automaticas_no_pasadas_ni_manuales(
        self, template, status, room, person
    ):
        from apps.appointments.models import Appointment
        futuro = date.today() + timedelta(days=7)
        pasado = date.today() - timedelta(days=7)
        s_fut = self._slot(template, status, room, futuro)
        s_pas = self._slot(template, status, room, pasado)
        s_man = self._slot(template, status, room, date.today() + timedelta(days=14))

        fs = FixedSlot.objects.create(person=person, template=template, start_date=pasado)
        # automáticas (futura + pasada)
        auto_fut = Appointment.objects.create(person=person, slot=s_fut, reserved=False, fixed_slot=fs)
        auto_pas = Appointment.objects.create(person=person, slot=s_pas, reserved=False, fixed_slot=fs)
        # manual futura (fixed_slot None)
        manual = Appointment.objects.create(person=person, slot=s_man, reserved=False)
        s_fut.availability = 9; s_fut.save(update_fields=['availability'])

        fs.delete()

        auto_fut.refresh_from_db(); auto_pas.refresh_from_db(); manual.refresh_from_db()
        s_fut.refresh_from_db()
        assert auto_fut.deleted is not None      # futura automática: cancelada
        assert auto_pas.deleted is None          # pasada: intacta
        assert manual.deleted is None            # manual: intacta
        assert s_fut.availability == 10          # availability devuelta

    def test_revivir_turno_fijo_regenera_reservas(
        self, admin_client, template, status, room, person, monkeypatch
    ):
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kw: None)
        from apps.appointments.models import Appointment
        s = self._slot(template, status, room, date.today() + timedelta(days=7))
        payload = {
            'person': person.id, 'template_id': template.id,
            'start_date': date.today().isoformat(),
        }
        r1 = admin_client.post(reverse(self.URL), data=payload, format='json')
        assert r1.status_code == 201
        fs = FixedSlot.all_objects.get(pk=r1.data['id'])
        fs.delete()
        assert Appointment.objects.filter(fixed_slot=fs, deleted__isnull=True).count() == 0
        # revivir por el mismo (person, template)
        r2 = admin_client.post(reverse(self.URL), data=payload, format='json')
        assert r2.status_code == 201
        assert r2.data['id'] == fs.pk
        assert Appointment.objects.filter(fixed_slot=fs, deleted__isnull=True).count() == 1


# Validar capacidad de sala
# La disponibilidad (availability) nunca debe superar room.capacity, en:
# creación de slot, edición de slot, creación/edición de template, y
# generación masiva desde template (fisura: la sala pudo reducir su capacidad).

@pytest.mark.django_db
class TestSlotRoomCapacity:
    SLOT_URL = 'slots-list'
    TEMPLATE_URL = 'slot-templates-list'
    GEN_URL = 'generate-slots-list'

    @pytest.fixture
    def lunes(self, db):
        w, _ = Week.objects.get_or_create(day='Lunes')
        return w

    @pytest.fixture
    def room_cap(self, studio):
        from apps.rooms.models import Room
        return Room.objects.create(name='Sala Cap', studio=studio, capacity=10)

    # Creación de slot
    def test_create_slot_exceeding_capacity_returns_400(self, admin_client, room_cap, status):
        next_monday = _next_weekday(0)
        response = admin_client.post(reverse(self.SLOT_URL), data={
            'date': next_monday.isoformat(),
            'start_time': '09:00:00',
            'end_time': '10:00:00',
            'status_id': status.id,
            'room': room_cap.id,
            'availability': 11,
        }, format='json')
        assert response.status_code == 400
        assert 'capacidad' in response.data['detail'].lower()

    def test_create_slot_at_capacity_boundary_succeeds(self, admin_client, room_cap, status):
        next_monday = _next_weekday(0)
        response = admin_client.post(reverse(self.SLOT_URL), data={
            'date': next_monday.isoformat(),
            'start_time': '11:00:00',
            'end_time': '12:00:00',
            'status_id': status.id,
            'room': room_cap.id,
            'availability': 10,
        }, format='json')
        assert response.status_code == 201

    def test_create_slot_room_without_capacity_is_unrestricted(self, admin_client, room, status):
        """Control negativo: sala con capacity=None no impone límite."""
        next_monday = _next_weekday(0)
        response = admin_client.post(reverse(self.SLOT_URL), data={
            'date': next_monday.isoformat(),
            'start_time': '13:00:00',
            'end_time': '14:00:00',
            'status_id': status.id,
            'room': room.id,
            'availability': 999,
        }, format='json')
        assert response.status_code == 201

    def test_create_slot_negative_availability_returns_400(self, admin_client, room_cap, status):
        next_monday = _next_weekday(0)
        response = admin_client.post(reverse(self.SLOT_URL), data={
            'date': next_monday.isoformat(),
            'start_time': '15:00:00',
            'end_time': '16:00:00',
            'status_id': status.id,
            'room': room_cap.id,
            'availability': -1,
        }, format='json')
        assert response.status_code == 400
        assert not Slot.objects.filter(start_time=time(15, 0), room=room_cap).exists()

    def test_create_slot_non_numeric_availability_returns_400(self, admin_client, room_cap, status):
        next_monday = _next_weekday(0)
        response = admin_client.post(reverse(self.SLOT_URL), data={
            'date': next_monday.isoformat(),
            'start_time': '16:00:00',
            'end_time': '17:00:00',
            'status_id': status.id,
            'room': room_cap.id,
            'availability': 'abc',
        }, format='json')
        assert response.status_code == 400

    # Edición de slot
    def test_update_slot_exceeding_capacity_returns_400(self, admin_client, room_cap, status):
        slot = Slot.objects.create(
            date=_next_weekday(0), start_time=time(9, 0), end_time=time(10, 0),
            status=status, room=room_cap, availability=10,
        )
        url = reverse('slots-detail', args=[slot.pk])
        response = admin_client.patch(url, data={'availability': 11}, format='json')
        assert response.status_code == 400
        assert 'capacidad' in response.data['detail'].lower()

    def test_update_slot_non_numeric_availability_returns_400(self, admin_client, room_cap, status):
        slot = Slot.objects.create(
            date=_next_weekday(0), start_time=time(9, 0), end_time=time(10, 0),
            status=status, room=room_cap, availability=10,
        )
        url = reverse('slots-detail', args=[slot.pk])
        response = admin_client.patch(url, data={'availability': 'abc'}, format='json')
        assert response.status_code == 400

    # Templates
    def test_create_template_exceeding_capacity_returns_400(self, admin_client, room_cap, lunes):
        response = admin_client.post(reverse(self.TEMPLATE_URL), data={
            'days_of_week_ids': [lunes.id],
            'start_time': '09:00:00',
            'end_time': '10:00:00',
            'room': room_cap.id,
            'availability': 11,
        }, format='json')
        assert response.status_code == 400
        assert 'capacidad' in response.data['detail'].lower()

    def test_create_template_at_capacity_boundary_succeeds(self, admin_client, room_cap, lunes):
        response = admin_client.post(reverse(self.TEMPLATE_URL), data={
            'days_of_week_ids': [lunes.id],
            'start_time': '09:00:00',
            'end_time': '10:00:00',
            'room': room_cap.id,
            'availability': 10,
        }, format='json')
        assert response.status_code == 201

    # Generación masiva (fisura)
    def test_generation_exceeding_capacity_returns_400_and_creates_nothing(
        self, admin_client, room_cap, lunes
    ):
        # Template creado por ORM con availability > capacity (simula que la sala
        # redujo su capacidad después de crear el template).
        template = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0),
            room=room_cap, availability=11,
        )
        template.days_of_week.set([lunes])
        today = date.today()
        response = admin_client.post(reverse(self.GEN_URL), data={
            'template_id': template.pk,
            'date_from': today.isoformat(),
            'date_to': (today + relativedelta(months=3)).isoformat(),
        }, format='json')
        assert response.status_code == 400
        assert 'capacidad' in response.data['detail'].lower()
        assert Slot.objects.filter(template=template).count() == 0


@pytest.mark.django_db
class TestCancelUnreservedSlotsOnDates:
    """cancel_unreserved_slots_on_dates(dates, floor=today): soft-deletea los Slot
    sin reserva en esas fechas (>= floor) y protege/reporta los que tienen reserva."""

    def _slot(self, status, room, d):
        return Slot.objects.create(
            status=status, room=room, date=d,
            start_time=time(9, 0), end_time=time(10, 0), availability=10,
        )

    def test_cancels_unreserved_slot(self, status, room):
        from apps.slots.services import cancel_unreserved_slots_on_dates
        d = date.today() + timedelta(days=5)
        slot = self._slot(status, room, d)
        cancelled, protected = cancel_unreserved_slots_on_dates({d})
        assert cancelled == 1
        assert protected == []
        assert not Slot.objects.filter(pk=slot.pk).exists()
        assert Slot.all_objects.get(pk=slot.pk).deleted is not None

    def test_protects_reserved_slot(self, status, room, person):
        from apps.slots.services import cancel_unreserved_slots_on_dates
        from apps.appointments.models import Appointment
        d = date.today() + timedelta(days=5)
        slot = self._slot(status, room, d)
        Appointment.objects.create(person=person, slot=slot, reserved=False)
        cancelled, protected = cancel_unreserved_slots_on_dates({d})
        assert cancelled == 0
        assert Slot.objects.filter(pk=slot.pk).exists()  # NO se borró
        assert protected == [{'date': d.isoformat(), 'slot': slot.id, 'reason': 'tiene_reservas'}]

    def test_ignores_past_slots(self, status, room):
        from apps.slots.services import cancel_unreserved_slots_on_dates
        d = date.today() - timedelta(days=3)
        slot = self._slot(status, room, d)
        cancelled, protected = cancel_unreserved_slots_on_dates({d})
        assert cancelled == 0
        assert Slot.objects.filter(pk=slot.pk).exists()  # pasado, intacto

    def test_ignores_dates_not_in_set(self, status, room):
        from apps.slots.services import cancel_unreserved_slots_on_dates
        d_holiday = date.today() + timedelta(days=5)
        d_other = date.today() + timedelta(days=6)
        slot_other = self._slot(status, room, d_other)
        cancelled, protected = cancel_unreserved_slots_on_dates({d_holiday})
        assert cancelled == 0
        assert Slot.objects.filter(pk=slot_other.pk).exists()

    def test_mixed_cancels_unreserved_and_protects_reserved(self, status, room, person):
        from apps.slots.services import cancel_unreserved_slots_on_dates
        from apps.appointments.models import Appointment
        d1 = date.today() + timedelta(days=5)
        d2 = date.today() + timedelta(days=6)
        free = self._slot(status, room, d1)
        reserved = self._slot(status, room, d2)
        Appointment.objects.create(person=person, slot=reserved, reserved=False)
        cancelled, protected = cancel_unreserved_slots_on_dates({d1, d2})
        assert cancelled == 1
        assert not Slot.objects.filter(pk=free.pk).exists()
        assert Slot.objects.filter(pk=reserved.pk).exists()
        assert protected == [{'date': d2.isoformat(), 'slot': reserved.id, 'reason': 'tiene_reservas'}]

    def test_soft_deleted_appointment_does_not_protect(self, status, room, person):
        """Si la única reserva del slot está soft-deleteada, el slot se cancela."""
        from apps.slots.services import cancel_unreserved_slots_on_dates
        from apps.appointments.models import Appointment
        d = date.today() + timedelta(days=5)
        slot = self._slot(status, room, d)
        appt = Appointment.objects.create(person=person, slot=slot, reserved=False)
        appt.delete()
        cancelled, protected = cancel_unreserved_slots_on_dates({d})
        assert cancelled == 1
        assert protected == []
        assert not Slot.objects.filter(pk=slot.pk).exists()


@pytest.mark.django_db
class TestSlotGenerationHolidays:
    """La generación omite fechas de feriado, cancela slots sin reserva que caigan
    en feriado y protege/reporta los que tienen reserva."""
    GEN_URL = 'generate-slots-list'

    @pytest.fixture(autouse=True)
    def _mock_action_audit(self, monkeypatch):
        """Action usa ArrayField (Postgres): no persiste en sqlite. Se mockea por
        default; el test de auditoría lo sobreescribe con su captura."""
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kw: None)

    def _monday_template(self, room):
        lunes = Week.objects.create(day='Lunes')
        t = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0), room=room, availability=10,
        )
        t.days_of_week.set([lunes])
        return t

    def _post(self, admin_client, t):
        today = date.today()
        return admin_client.post(reverse(self.GEN_URL), data={
            'template_id': t.pk,
            'date_from': today.isoformat(),
            'date_to': (today + relativedelta(months=3)).isoformat(),
        }, format='json')

    def test_does_not_generate_on_holiday(self, admin_client, status, room):
        from apps.holidays.models import Holiday
        t = self._monday_template(room)
        holiday_monday = _next_weekday(0)
        Holiday.objects.create(name='Feriado', start_date=holiday_monday)

        resp = self._post(admin_client, t)
        assert resp.status_code == 201
        assert not Slot.objects.filter(template=t, date=holiday_monday).exists()
        assert Slot.objects.filter(template=t).exists()  # sí generó otros lunes
        assert resp.data['feriados_omitidos'] >= 1

    def test_cancels_existing_unreserved_slot_on_holiday(self, admin_client, status, room):
        from apps.holidays.models import Holiday
        t = self._monday_template(room)
        holiday_monday = _next_weekday(0)
        slot = Slot.objects.create(
            template=t, date=holiday_monday, start_time=time(9, 0),
            end_time=time(10, 0), room=room, availability=10, status=status,
        )
        Holiday.objects.create(name='Feriado', start_date=holiday_monday)

        resp = self._post(admin_client, t)
        assert resp.status_code == 201
        assert not Slot.objects.filter(pk=slot.pk).exists()  # cancelado
        assert resp.data['slots_cancelados'] >= 1

    def test_protects_reserved_slot_on_holiday(self, admin_client, status, room, person):
        from apps.holidays.models import Holiday
        from apps.appointments.models import Appointment
        t = self._monday_template(room)
        holiday_monday = _next_weekday(0)
        slot = Slot.objects.create(
            template=t, date=holiday_monday, start_time=time(9, 0),
            end_time=time(10, 0), room=room, availability=10, status=status,
        )
        Appointment.objects.create(person=person, slot=slot, reserved=False)
        Holiday.objects.create(name='Feriado', start_date=holiday_monday)

        resp = self._post(admin_client, t)
        assert resp.status_code == 201
        assert Slot.objects.filter(pk=slot.pk).exists()  # protegido, no borrado
        assert any(p['slot'] == slot.id for p in resp.data['slots_protegidos'])

    def test_cancellation_registers_action(self, admin_client, status, room, monkeypatch):
        from apps.actions.models import Action
        from apps.holidays.models import Holiday
        capturados = []
        monkeypatch.setattr(Action.objects, "create", lambda **kw: capturados.append(kw))
        t = self._monday_template(room)
        holiday_monday = _next_weekday(0)
        Slot.objects.create(
            template=t, date=holiday_monday, start_time=time(9, 0),
            end_time=time(10, 0), room=room, availability=10, status=status,
        )
        Holiday.objects.create(name='Feriado', start_date=holiday_monday)

        resp = self._post(admin_client, t)
        assert resp.status_code == 201
        assert any('feriado' in str(kw.get('target', '')).lower() for kw in capturados)


@pytest.mark.django_db
class TestSeedSlotsHolidays:
    """El comando de seed tampoco genera slots en fechas de feriado."""

    def test_seed_generation_skips_holidays(self, status, room):
        from apps.slots.management.commands.seed_slots import Command
        from apps.holidays.models import Holiday
        lunes = Week.objects.create(id=1, day='Lunes')  # seed mapea week_id = weekday()+1
        t = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0), room=room, availability=10,
        )
        t.days_of_week.set([lunes])
        holiday_monday = _next_weekday(0)
        Holiday.objects.create(name='Feriado', start_date=holiday_monday)

        Command()._generate_slots(t, date.today(), date.today() + timedelta(days=30))

        assert not Slot.objects.filter(template=t, date=holiday_monday).exists()
        assert Slot.objects.filter(template=t).exists()


@pytest.mark.django_db
class TestSlotRestore:
    """POST /slots/{id}/restore/ restaura un slot dado de baja (soft-delete),
    salvo que su fecha siga siendo feriado."""
    RESTORE_URL = 'slots-restore'

    def _deleted_slot(self, status, room, d):
        slot = Slot.objects.create(
            status=status, room=room, date=d,
            start_time=time(9, 0), end_time=time(10, 0), availability=10,
        )
        slot.delete()
        return slot

    def test_restore_soft_deleted_slot(self, admin_client, status, room):
        d = date.today() + timedelta(days=5)
        slot = self._deleted_slot(status, room, d)
        resp = admin_client.post(reverse(self.RESTORE_URL, args=[slot.pk]))
        assert resp.status_code == 200
        assert Slot.objects.filter(pk=slot.pk).exists()  # activo de nuevo
        slot.refresh_from_db()
        assert slot.deleted is None

    def test_restore_non_deleted_returns_400(self, admin_client, status, room):
        d = date.today() + timedelta(days=5)
        slot = Slot.objects.create(
            status=status, room=room, date=d,
            start_time=time(9, 0), end_time=time(10, 0), availability=10,
        )
        resp = admin_client.post(reverse(self.RESTORE_URL, args=[slot.pk]))
        assert resp.status_code == 400

    def test_restore_on_holiday_date_returns_400(self, admin_client, status, room):
        from apps.holidays.models import Holiday
        d = date.today() + timedelta(days=5)
        slot = self._deleted_slot(status, room, d)
        Holiday.objects.create(name='Feriado', start_date=d)
        resp = admin_client.post(reverse(self.RESTORE_URL, args=[slot.pk]))
        assert resp.status_code == 400
        slot.refresh_from_db()
        assert slot.deleted is not None  # sigue de baja

    def test_restore_works_for_consultor(self, consultor_client, status, room):
        d = date.today() + timedelta(days=5)
        slot = self._deleted_slot(status, room, d)
        resp = consultor_client.post(reverse(self.RESTORE_URL, args=[slot.pk]))
        assert resp.status_code == 200
        assert Slot.objects.filter(pk=slot.pk).exists()


@pytest.mark.django_db
class TestFixedSlotConsumeSession:
    def _plan(self, person, plans_subtype_a, sessions):
        from datetime import timedelta
        from django.utils import timezone
        from apps.people.models import PersonActivePlan
        return PersonActivePlan.objects.create(
            person=person, plans_subtype=plans_subtype_a,
            exp_date=timezone.now().date() + timedelta(days=60),
            sessions_total=sessions, sessions_remaining=sessions,
        )

    def test_reserve_person_in_slot_descuenta(self, person, slot_with_activity, plans_subtype_a):
        from apps.slots.models import reserve_person_in_slot
        plan = self._plan(person, plans_subtype_a, 5)
        estado = reserve_person_in_slot(person, slot_with_activity, None)
        assert estado == "creado"
        plan.refresh_from_db()
        assert plan.sessions_remaining == 4
        from apps.appointments.models import Appointment
        appt = Appointment.objects.get(person=person, slot=slot_with_activity)
        assert appt.consumed_plan_id == plan.id

    def test_reserve_person_in_slot_sin_sesiones(self, person, slot_with_activity, plans_subtype_a):
        from apps.slots.models import reserve_person_in_slot
        self._plan(person, plans_subtype_a, 0)
        estado = reserve_person_in_slot(person, slot_with_activity, None)
        assert estado == "sin_sesiones"
        from apps.appointments.models import Appointment
        assert not Appointment.objects.filter(person=person, slot=slot_with_activity).exists()

    def test_fixedslot_delete_devuelve_sesiones(self, person, plans_subtype_a, room, status):
        from datetime import timedelta, time
        from django.utils import timezone
        from apps.slots.models import Slot, SlotTemplate, FixedSlot, reserve_person_in_slot
        plan = self._plan(person, plans_subtype_a, 5)
        t = SlotTemplate.objects.create(start_time=time(9, 0), end_time=time(10, 0),
                                        room=room, availability=10,
                                        activity_subtype=plans_subtype_a.activity_subtype)
        futuro = timezone.now().date() + timedelta(days=7)
        s = Slot.objects.create(template=t, date=futuro, start_time=time(9, 0),
                                end_time=time(10, 0), room=room, availability=10,
                                activity_subtype=plans_subtype_a.activity_subtype, status=status)
        fs = FixedSlot.objects.create(person=person, template=t, start_date=futuro)
        reserve_person_in_slot(person, s, fs)
        plan.refresh_from_db(); assert plan.sessions_remaining == 4
        fs.delete()
        plan.refresh_from_db(); assert plan.sessions_remaining == 5  # devuelta


@pytest.mark.django_db
class TestSlotUpdateNullFieldsKAN168:
    """Editar un slot no debe romper (500) cuando availability/status son NULL,
    y la auto-gestión de status debe persistir (bug key status vs status_id)."""

    def test_patch_slot_con_availability_y_status_nulos_no_500(self, admin_client, room):
        slot = Slot.objects.create(
            room=room, date=date.today() + timedelta(days=1),
            start_time=time(10, 0), end_time=time(11, 0),
        )  # availability=None, status=None, sin reservas
        resp = admin_client.patch(
            reverse('slots-detail', args=[slot.pk]),
            data={'end_time': '11:30:00'}, format='json',
        )
        assert resp.status_code == 200, resp.data

    def test_patch_availability_cero_marca_lleno(self, admin_client, status, room):
        from apps.status.models import Status
        Status.objects.get_or_create(id=2, defaults={'status': 'Lleno'})
        slot = Slot.objects.create(
            status=status, room=room, date=date.today() + timedelta(days=1),
            start_time=time(9, 0), end_time=time(10, 0), availability=5,
        )
        resp = admin_client.patch(
            reverse('slots-detail', args=[slot.pk]),
            data={'availability': 0}, format='json',
        )
        assert resp.status_code == 200, resp.data
        slot.refresh_from_db()
        assert slot.status_id == 2  # LLENO ahora persiste (antes se descartaba)

    def test_patch_availability_positiva_marca_disponible(self, admin_client, room):
        from apps.status.models import Status
        Status.objects.get_or_create(id=1, defaults={'status': 'Disponible'})
        lleno, _ = Status.objects.get_or_create(id=2, defaults={'status': 'Lleno'})
        slot = Slot.objects.create(
            status=lleno, room=room, date=date.today() + timedelta(days=1),
            start_time=time(9, 0), end_time=time(10, 0), availability=0,
        )
        resp = admin_client.patch(
            reverse('slots-detail', args=[slot.pk]),
            data={'availability': 3}, format='json',
        )
        assert resp.status_code == 200, resp.data
        slot.refresh_from_db()
        assert slot.status_id == 1  # DISPONIBLE


@pytest.mark.django_db
class TestGenerateSlotsDefaultKAN169:
    """El endpoint /generate-slots/ sin fechas genera hoy -> hoy + 3 meses."""
    URL = 'generate-slots-list'

    @pytest.fixture
    def lunes(self, db):
        w, _ = Week.objects.get_or_create(day='Lunes')
        return w

    @pytest.fixture
    def template(self, lunes, room):
        t = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0), room=room, availability=10,
        )
        t.days_of_week.set([lunes])
        return t

    def test_sin_fechas_genera_hasta_3_meses(self, admin_client, template, status):
        resp = admin_client.post(reverse(self.URL), data={'template_id': template.pk}, format='json')
        assert resp.status_code == 201
        today = date.today()
        limite = today + relativedelta(months=3)
        assert Slot.objects.filter(template=template, date__gte=today).exists()
        # No genera más allá de hoy + 3 meses
        assert not Slot.objects.filter(template=template, date__gt=limite).exists()
        # Y llega hasta el 3er mes (último lunes ≤ hoy+3m, dentro de la última semana)
        last = Slot.objects.filter(template=template).order_by('-date').first()
        assert limite - timedelta(days=7) <= last.date <= limite


@pytest.mark.django_db
class TestGenerateSlotsCommandKAN169:
    """El command generate_slots crea slots hoy -> +3m para todos los templates
    activos, idempotente, omitiendo los inactivos."""

    @pytest.fixture
    def lunes(self, db):
        w, _ = Week.objects.get_or_create(day='Lunes')
        return w

    def _template(self, lunes, room, start, active=True):
        t = SlotTemplate.objects.create(
            start_time=start, end_time=time(start.hour + 1, 0),
            room=room, availability=10, is_active=active,
        )
        t.days_of_week.set([lunes])
        return t

    def test_genera_activos_omite_inactivos(self, status, room, lunes):
        from django.core.management import call_command
        activo = self._template(lunes, room, time(9, 0), active=True)
        inactivo = self._template(lunes, room, time(11, 0), active=False)
        call_command('generate_slots')
        today = date.today()
        assert Slot.objects.filter(template=activo, date__gte=today).exists()
        assert not Slot.objects.filter(template=inactivo).exists()
        last = Slot.objects.filter(template=activo).order_by('-date').first()
        assert last.date >= today + relativedelta(months=3) - timedelta(days=7)

    def test_command_es_idempotente(self, status, room, lunes):
        from django.core.management import call_command
        t = self._template(lunes, room, time(9, 0), active=True)
        call_command('generate_slots')
        n1 = Slot.objects.filter(template=t).count()
        call_command('generate_slots')
        n2 = Slot.objects.filter(template=t).count()
        assert n1 > 0 and n2 == n1

    def test_command_sin_templates_activos_no_falla(self, status, db):
        from django.core.management import call_command
        call_command('generate_slots')  # no debe lanzar
        assert Slot.objects.count() == 0

    def test_command_omite_template_sin_capacidad(self, status, studio, lunes):
        from django.core.management import call_command
        from apps.rooms.models import Room
        sala_chica = Room.objects.create(name='Chica', studio=studio, capacity=5)
        t = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0),
            room=sala_chica, availability=10, is_active=True,  # 10 > capacidad 5
        )
        t.days_of_week.set([lunes])
        call_command('generate_slots')
        assert not Slot.objects.filter(template=t).exists()


# campo read-only `teachers` en SlotSerializer

@pytest.mark.django_db
class TestSlotTeachersFieldKAN281:
    """El SlotSerializer expone `teachers` (read-only) con los docentes asignados
    al slot vía la relación teachers_turn: lista de {rol, teacher:{id,name,last_name}}.
    Excluye asignaciones soft-deleted; [] si no hay ninguna."""

    def _make_turn(self, slot, teacher, rol='Instructor', deleted=None):
        from apps.teachers_turn.models import TeachersTurn
        return TeachersTurn.objects.create(
            slot=slot, teacher=teacher, rol=rol, deleted=deleted,
        )

    def test_serializer_includes_teachers(self, slot, teacher):
        self._make_turn(slot, teacher, rol='Instructor')
        data = SlotSerializer(slot).data
        assert data['teachers'] == [
            {'rol': 'Instructor',
             'teacher': {'id': teacher.id, 'name': teacher.name, 'last_name': teacher.last_name}}
        ]

    def test_serializer_no_teachers_returns_empty_list(self, slot):
        data = SlotSerializer(slot).data
        assert data['teachers'] == []

    def test_serializer_excludes_deleted_turn(self, slot, teacher):
        from django.utils import timezone
        self._make_turn(slot, teacher, rol='Instructor', deleted=timezone.now())
        data = SlotSerializer(slot).data
        assert data['teachers'] == []

    def test_serializer_multiple_teachers(self, slot, teacher):
        otro = Teacher.objects.create(name='Beto', last_name='Lopez', dni='22222222')
        self._make_turn(slot, teacher, rol='Instructor')
        self._make_turn(slot, otro, rol='Asistente')
        data = SlotSerializer(slot).data
        roles = {t['rol']: t['teacher']['name'] for t in data['teachers']}
        assert roles == {'Instructor': 'Ana', 'Asistente': 'Beto'}

    def test_serializer_turn_without_teacher(self, slot):
        # teacher es nullable en TeachersTurn: el turno sin docente expone teacher=None
        self._make_turn(slot, None, rol='Recepcion')
        data = SlotSerializer(slot).data
        assert data['teachers'] == [{'rol': 'Recepcion', 'teacher': None}]

    def test_slots_endpoint_exposes_teachers(self, admin_client, slot, teacher):
        self._make_turn(slot, teacher, rol='Instructor')
        resp = admin_client.get(reverse('slots-detail', args=[slot.pk]))
        assert resp.status_code == 200
        assert resp.data['teachers'] == [
            {'rol': 'Instructor',
             'teacher': {'id': teacher.id, 'name': teacher.name, 'last_name': teacher.last_name}}
        ]

    def test_appointments_endpoint_exposes_slot_teachers(self, admin_client, slot, teacher, person):
        from apps.appointments.models import Appointment
        self._make_turn(slot, teacher, rol='Instructor')
        Appointment.objects.create(slot=slot, person=person)
        resp = admin_client.get(reverse('appointments-list'))
        assert resp.status_code == 200
        results = resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data
        assert results[0]['slot']['teachers'] == [
            {'rol': 'Instructor',
             'teacher': {'id': teacher.id, 'name': teacher.name, 'last_name': teacher.last_name}}
        ]

    def test_slots_list_avoids_n_plus_1(self, admin_client, status, room, teacher, django_assert_max_num_queries):
        # Dos slots, cada uno con una asignación de docente: el nº de queries no
        # debe crecer con la cantidad de slots (prefetch_related)..
        from apps.teachers_turn.models import TeachersTurn
        for i in range(2):
            s = Slot.objects.create(
                status=status, room=room,
                date=date.today() + timedelta(days=10 + i),
                start_time=time(9, 0), end_time=time(10, 0), availability=10,
            )
            TeachersTurn.objects.create(slot=s, teacher=teacher, rol='Instructor')
        with django_assert_max_num_queries(12):
            resp = admin_client.get(reverse('slots-list'))
        assert resp.status_code == 200
