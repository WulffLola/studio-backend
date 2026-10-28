import pytest
from datetime import date
from django.urls import reverse
from .models import Holiday


@pytest.mark.django_db
class TestHolidaySoftDelete:

    def test_delete_sets_deleted(self):
        holiday = Holiday.objects.create(name='Año Nuevo', start_date='2025-01-01')
        holiday.delete()
        holiday.refresh_from_db()
        assert holiday.deleted is not None

    def test_objects_hides_deleted(self):
        holiday = Holiday.objects.create(name='Año Nuevo', start_date='2025-01-01')
        holiday.delete()
        assert not Holiday.objects.filter(pk=holiday.pk).exists()

    def test_all_objects_includes_deleted(self):
        holiday = Holiday.objects.create(name='Año Nuevo', start_date='2025-01-01')
        holiday.delete()
        assert Holiday.all_objects.filter(pk=holiday.pk).exists()

    def test_restore(self):
        holiday = Holiday.objects.create(name='Año Nuevo', start_date='2025-01-01')
        holiday.delete()
        holiday.restore()
        holiday.refresh_from_db()
        assert holiday.deleted is None

    def test_hard_delete_removes_from_db(self):
        holiday = Holiday.objects.create(name='Año Nuevo', start_date='2025-01-01')
        pk = holiday.pk
        holiday.hard_delete()
        assert not Holiday.all_objects.filter(pk=pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user):
        holiday = Holiday.objects.create(name='Año Nuevo', start_date='2025-01-01')
        holiday.delete()
        qs = Holiday.all_objects.for_user(admin_user)
        assert qs.filter(pk=holiday.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user):
        holiday = Holiday.objects.create(name='Año Nuevo', start_date='2025-01-01')
        holiday.delete()
        qs = Holiday.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=holiday.pk).exists()


@pytest.mark.django_db
class TestHolidayModel:

    def test_single_day_has_no_end_date(self):
        """Un feriado de un día se crea solo con start_date."""
        holiday = Holiday.objects.create(name='Navidad', start_date='2025-12-25')
        assert holiday.end_date is None

    def test_range_stores_start_and_end(self):
        """Un rango de fechas guarda ambos campos en una sola fila."""
        holiday = Holiday.objects.create(
            name='Vacaciones', start_date='2026-01-01', end_date='2026-01-14'
        )
        holiday.refresh_from_db()
        assert str(holiday.start_date) == '2026-01-01'
        assert str(holiday.end_date) == '2026-01-14'

    def test_str_single_day(self):
        h = Holiday.objects.create(name='Navidad', start_date='2025-12-25')
        assert 'Navidad' in str(h)
        assert '2025-12-25' in str(h)

    def test_str_range(self):
        h = Holiday.objects.create(name='Vacaciones', start_date='2026-01-01', end_date='2026-01-14')
        assert '→' in str(h)


@pytest.mark.django_db
class TestHolidayViewSet:
    LIST_URL = 'holidays-list'
    DETAIL_URL = 'holidays-detail'

    def test_create_single_day(self, admin_client):
        """POST con solo start_date crea un feriado de un día."""
        response = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Navidad', 'start_date': '2026-12-25'},
            format='json',
        )
        assert response.status_code == 201
        assert response.data['end_date'] is None

    def test_create_range(self, admin_client):
        """POST con start_date y end_date crea un período en una sola fila."""
        response = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Vacaciones', 'start_date': '2026-07-01', 'end_date': '2026-07-14'},
            format='json',
        )
        assert response.status_code == 201
        assert response.data['start_date'] == '2026-07-01'
        assert response.data['end_date'] == '2026-07-14'
        assert Holiday.objects.count() == 1

    def test_end_date_before_start_date_returns_400(self, admin_client):
        """end_date anterior a start_date debe rechazarse."""
        response = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Error', 'start_date': '2026-01-14', 'end_date': '2026-01-01'},
            format='json',
        )
        assert response.status_code == 400
        assert 'end_date' in response.data

    def test_same_day_range_is_valid(self, admin_client):
        """start_date == end_date es válido (equivale a un día único)."""
        response = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Feriado', 'start_date': '2026-05-01', 'end_date': '2026-05-01'},
            format='json',
        )
        assert response.status_code == 201

    def test_admin_sees_deleted_in_list(self, admin_client):
        from datetime import date
        year = date.today().year
        holiday = Holiday.objects.create(name='Navidad', start_date=f'{year}-12-25')
        holiday.delete()
        response = admin_client.get(reverse(self.LIST_URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert holiday.id in ids

    def test_consultor_excludes_deleted(self, consultor_client):
        from datetime import date
        year = date.today().year
        holiday = Holiday.objects.create(name='Navidad', start_date=f'{year}-12-25')
        holiday.delete()
        response = consultor_client.get(reverse(self.LIST_URL))
        ids = [item['id'] for item in response.data]
        assert holiday.id not in ids

    def test_delete_endpoint_is_soft_delete(self, admin_client):
        from datetime import date
        holiday = Holiday.objects.create(name='Carnaval', start_date=f'{date.today().year}-03-03')
        response = admin_client.delete(reverse(self.DETAIL_URL, args=[holiday.pk]))
        assert response.status_code == 204
        holiday.refresh_from_db()
        assert holiday.deleted is not None

    def test_response_includes_start_and_end_date(self, admin_client):
        """La respuesta expone ambos campos para que el frontend los distinga."""
        from datetime import date
        Holiday.objects.create(name='Semana Santa', start_date=f'{date.today().year}-04-01', end_date=f'{date.today().year}-04-05')
        response = admin_client.get(reverse(self.LIST_URL))
        item = response.data[0]
        assert 'start_date' in item
        assert 'end_date' in item

    def test_only_current_year_returned(self, admin_client):
        """El listado solo devuelve feriados del año en curso."""
        from datetime import date
        year = date.today().year
        current = Holiday.objects.create(name='Actual', start_date=f'{year}-06-01')
        past = Holiday.objects.create(name='Pasado', start_date=f'{year - 1}-06-01')
        response = admin_client.get(reverse(self.LIST_URL))
        ids = [item['id'] for item in response.data]
        assert current.id in ids
        assert past.id not in ids

    def test_duplicate_single_day_returns_400(self, admin_client):
        """Dos feriados no pueden tener la misma fecha."""
        from datetime import date
        year = date.today().year
        Holiday.objects.create(name='Navidad', start_date=f'{year}-12-25')
        response = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Otro evento', 'start_date': f'{year}-12-25'},
            format='json',
        )
        assert response.status_code == 400

    def test_overlapping_range_returns_400(self, admin_client):
        """Un rango no puede solaparse con uno existente."""
        from datetime import date
        year = date.today().year
        Holiday.objects.create(name='Vacaciones', start_date=f'{year}-07-01', end_date=f'{year}-07-14')
        response = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Overlap', 'start_date': f'{year}-07-10', 'end_date': f'{year}-07-20'},
            format='json',
        )
        assert response.status_code == 400

    def test_adjacent_ranges_do_not_overlap(self, admin_client):
        """Rangos contiguos (uno termina donde el otro empieza) son válidos."""
        from datetime import date
        year = date.today().year
        Holiday.objects.create(name='Vacaciones julio', start_date=f'{year}-07-01', end_date=f'{year}-07-14')
        response = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Vacaciones agosto', 'start_date': f'{year}-07-15', 'end_date': f'{year}-07-31'},
            format='json',
        )
        assert response.status_code == 201

    def test_same_date_different_years_allowed(self, admin_client):
        """El mismo día en distintos años no es duplicado (años anteriores no afectan)."""
        from datetime import date
        year = date.today().year
        Holiday.objects.create(name='Navidad pasada', start_date=f'{year - 1}-12-25')
        response = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Navidad', 'start_date': f'{year}-12-25'},
            format='json',
        )
        assert response.status_code == 201

    def test_soft_deleted_holiday_does_not_block_same_date(self, admin_client):
        """Una fecha eliminada (soft delete) no bloquea crear la misma fecha nuevamente."""
        from datetime import date
        year = date.today().year
        h = Holiday.objects.create(name='Navidad', start_date=f'{year}-12-25')
        h.delete()
        response = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Navidad (recreada)', 'start_date': f'{year}-12-25'},
            format='json',
        )
        assert response.status_code == 201


@pytest.mark.django_db
class TestHolidayDatesInRange:
    """holiday_dates_in_range(date_from, date_to): set de fechas cubiertas por
    algún feriado activo dentro de la ventana [date_from, date_to]."""

    def test_single_day_holiday_inside_window(self):
        from apps.holidays.services import holiday_dates_in_range
        Holiday.objects.create(name='Navidad', start_date=date(2026, 12, 25))
        result = holiday_dates_in_range(date(2026, 12, 1), date(2026, 12, 31))
        assert result == {date(2026, 12, 25)}

    def test_range_holiday_is_inclusive(self):
        from apps.holidays.services import holiday_dates_in_range
        Holiday.objects.create(
            name='Vacaciones', start_date=date(2026, 1, 1), end_date=date(2026, 1, 3),
        )
        result = holiday_dates_in_range(date(2026, 1, 1), date(2026, 1, 31))
        assert result == {date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)}

    def test_holiday_outside_window_excluded(self):
        from apps.holidays.services import holiday_dates_in_range
        Holiday.objects.create(name='Navidad', start_date=date(2026, 12, 25))
        result = holiday_dates_in_range(date(2026, 1, 1), date(2026, 6, 30))
        assert result == set()

    def test_range_partially_overlapping_is_clamped_to_window(self):
        from apps.holidays.services import holiday_dates_in_range
        Holiday.objects.create(
            name='Vacaciones', start_date=date(2025, 12, 28), end_date=date(2026, 1, 5),
        )
        result = holiday_dates_in_range(date(2026, 1, 1), date(2026, 1, 31))
        assert result == {date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3),
                          date(2026, 1, 4), date(2026, 1, 5)}

    def test_soft_deleted_holiday_excluded(self):
        from apps.holidays.services import holiday_dates_in_range
        h = Holiday.objects.create(name='Navidad', start_date=date(2026, 12, 25))
        h.delete()
        result = holiday_dates_in_range(date(2026, 12, 1), date(2026, 12, 31))
        assert result == set()


@pytest.mark.django_db
class TestHolidayCreationCancelsSlots:
    """Crear un feriado (POST /holidays/) cancela los slots futuros sin reserva en
    sus fechas y protege/reporta los reservados. No toca slots pasados."""
    LIST_URL = 'holidays-list'

    @pytest.fixture(autouse=True)
    def _mock_action_audit(self, monkeypatch):
        """Action usa ArrayField (Postgres): no persiste en sqlite. Se mockea por
        default; el test de auditoría lo sobreescribe con su captura."""
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kw: None)

    def _slot(self, status, room, d):
        from datetime import time
        from apps.slots.models import Slot
        return Slot.objects.create(
            status=status, room=room, date=d,
            start_time=time(9, 0), end_time=time(10, 0), availability=10,
        )

    def test_creating_holiday_cancels_future_unreserved_slot(self, admin_client, status, room):
        from datetime import timedelta
        from apps.slots.models import Slot
        d = date.today() + timedelta(days=7)
        slot = self._slot(status, room, d)
        resp = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Feriado', 'start_date': d.isoformat()}, format='json',
        )
        assert resp.status_code == 201
        assert not Slot.objects.filter(pk=slot.pk).exists()
        assert resp.data['slots_cancelados'] >= 1

    def test_creating_holiday_protects_reserved_slot(self, admin_client, status, room, person):
        from datetime import timedelta
        from apps.slots.models import Slot
        from apps.appointments.models import Appointment
        d = date.today() + timedelta(days=7)
        slot = self._slot(status, room, d)
        Appointment.objects.create(person=person, slot=slot, reserved=False)
        resp = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Feriado', 'start_date': d.isoformat()}, format='json',
        )
        assert resp.status_code == 201
        assert Slot.objects.filter(pk=slot.pk).exists()
        assert any(p['slot'] == slot.id for p in resp.data['slots_protegidos'])

    def test_creating_holiday_ignores_past_slot(self, admin_client, status, room):
        from datetime import timedelta
        from apps.slots.models import Slot
        d = date.today() - timedelta(days=3)
        slot = self._slot(status, room, d)
        resp = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Feriado pasado', 'start_date': d.isoformat()}, format='json',
        )
        assert resp.status_code == 201
        assert Slot.objects.filter(pk=slot.pk).exists()  # pasado, intacto

    def test_creating_range_holiday_cancels_all_dates(self, admin_client, status, room):
        from datetime import timedelta
        from apps.slots.models import Slot
        d1 = date.today() + timedelta(days=7)
        d2 = d1 + timedelta(days=2)
        s1 = self._slot(status, room, d1)
        s2 = self._slot(status, room, d2)
        resp = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Vacaciones', 'start_date': d1.isoformat(), 'end_date': d2.isoformat()},
            format='json',
        )
        assert resp.status_code == 201
        assert not Slot.objects.filter(pk=s1.pk).exists()
        assert not Slot.objects.filter(pk=s2.pk).exists()
        assert resp.data['slots_cancelados'] >= 2

    def test_cancellation_registers_action(self, admin_client, status, room, monkeypatch):
        from datetime import timedelta
        from apps.actions.models import Action
        capturados = []
        monkeypatch.setattr(Action.objects, "create", lambda **kw: capturados.append(kw))
        d = date.today() + timedelta(days=7)
        self._slot(status, room, d)
        resp = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Feriado', 'start_date': d.isoformat()}, format='json',
        )
        assert resp.status_code == 201
        assert any('feriado' in str(kw.get('target', '')).lower() for kw in capturados)

    def test_cancellation_failure_does_not_500(self, admin_client, status, room, monkeypatch):
        """Si la cancelación falla, el feriado igual se crea (201) y se reporta
        el problema en vez de devolver 500."""
        from datetime import timedelta
        from apps.slots.models import Slot
        import apps.holidays.views as holidays_views

        def _boom(*a, **kw):
            raise RuntimeError('fallo simulado')

        monkeypatch.setattr(holidays_views, 'cancel_unreserved_slots_on_dates', _boom, raising=False)
        d = date.today() + timedelta(days=7)
        self._slot(status, room, d)
        resp = admin_client.post(
            reverse(self.LIST_URL),
            data={'name': 'Feriado', 'start_date': d.isoformat()}, format='json',
        )
        assert resp.status_code == 201
        assert Holiday.objects.filter(name='Feriado').exists()
        assert resp.data['slots_cancelados'] is None


@pytest.mark.django_db
class TestHolidayUpdateCancelsSlots:
    """Editar un feriado (PATCH) para extender su rango cancela los slots sin
    reserva de los días nuevos."""
    DETAIL_URL = 'holidays-detail'

    @pytest.fixture(autouse=True)
    def _mock_action_audit(self, monkeypatch):
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kw: None)

    def _slot(self, status, room, d):
        from datetime import time
        from apps.slots.models import Slot
        return Slot.objects.create(
            status=status, room=room, date=d,
            start_time=time(9, 0), end_time=time(10, 0), availability=10,
        )

    def test_extending_range_cancels_slots_on_new_days(self, admin_client, status, room):
        from datetime import timedelta
        from apps.slots.models import Slot
        d1 = date.today() + timedelta(days=5)
        d2 = d1 + timedelta(days=2)
        holiday = Holiday.objects.create(name='Feriado', start_date=d1)
        slot = self._slot(status, room, d2)

        resp = admin_client.patch(
            reverse(self.DETAIL_URL, args=[holiday.pk]),
            data={'end_date': d2.isoformat()}, format='json',
        )
        assert resp.status_code == 200
        assert not Slot.objects.filter(pk=slot.pk).exists()
        assert resp.data['slots_cancelados'] >= 1

    def test_shortening_range_reports_freed_dates(self, admin_client, status, room):
        from datetime import timedelta
        d1 = date.today() + timedelta(days=5)
        d5 = d1 + timedelta(days=4)
        holiday = Holiday.objects.create(name='Vacaciones', start_date=d1, end_date=d5)
        d3 = d1 + timedelta(days=2)

        resp = admin_client.patch(
            reverse(self.DETAIL_URL, args=[holiday.pk]),
            data={'end_date': d3.isoformat()}, format='json',
        )
        assert resp.status_code == 200
        freed = resp.data['fechas_liberadas']
        assert (d1 + timedelta(days=3)).isoformat() in freed
        assert (d1 + timedelta(days=4)).isoformat() in freed

    def test_shortening_range_regenerates_slots_on_freed_dates(self, admin_client, status, room):
        """Al acortar un feriado, las fechas liberadas regeneran sus slots según
        los templates activos (no quedan 'perdidas' en silencio)."""
        from datetime import timedelta, time
        from apps.slots.models import Slot, SlotTemplate
        from apps.weeks.models import Week
        dias = [Week.objects.create(day=d) for d in
                ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']]
        t = SlotTemplate.objects.create(
            start_time=time(9, 0), end_time=time(10, 0), room=room, availability=10,
        )
        t.days_of_week.set(dias)
        d1 = date.today() + timedelta(days=5)
        d5 = d1 + timedelta(days=4)
        holiday = Holiday.objects.create(name='Vacaciones', start_date=d1, end_date=d5)
        d3 = d1 + timedelta(days=2)

        resp = admin_client.patch(
            reverse(self.DETAIL_URL, args=[holiday.pk]),
            data={'end_date': d3.isoformat()}, format='json',
        )
        assert resp.status_code == 200
        # fechas liberadas (d4, d5) regeneraron slot
        assert Slot.objects.filter(template=t, date=d1 + timedelta(days=3)).exists()
        assert Slot.objects.filter(template=t, date=d1 + timedelta(days=4)).exists()
        assert resp.data['slots_regenerados'] >= 2
        # fechas que siguen siendo feriado (d1..d3) NO regeneran
        assert not Slot.objects.filter(template=t, date=d1).exists()
