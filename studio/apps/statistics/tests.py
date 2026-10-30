import pytest
from datetime import date, time
from django.urls import reverse
from django.utils import timezone
from apps.payments.models import Payment, PaymentItem
from apps.people.models import PersonActivePlan


@pytest.mark.django_db
class TestClientsByPlanRepointed:
    """ /clients-by-plan/ agrupa por plans_subtype (PersonActivePlan)."""
    URL = 'clients-by-plan-list'

    def test_groups_by_plans_subtype(self, admin_client, person, plans_subtype_a):
        PersonActivePlan.objects.create(
            person=person, plans_subtype=plans_subtype_a,
            exp_date=date.today(), sessions_total=4, sessions_remaining=4,
        )
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        names = [row['plans_subtype__name'] for row in resp.data]
        assert plans_subtype_a.name in names


@pytest.mark.django_db
class TestMostProfitablePlanRepointed:
    """ /most-profitable-plan/ suma PaymentItem.final_amount por plans_subtype."""
    URL = 'most-profitable-plan-list'

    def test_sums_final_amount_by_subtype(self, admin_client, person, plans_subtype_a, studio):
        payment = Payment.objects.create(
            person=person, amount='1000', date=timezone.now(), method='Efectivo', studio=studio,
        )
        PaymentItem.objects.create(
            payment=payment, person=person, plans_subtype=plans_subtype_a,
            base_amount='1000.00', discount_pct='0',
        )
        year = timezone.now().year
        resp = admin_client.get(reverse(self.URL), {'year': str(year)})
        assert resp.status_code == 200
        top = resp.data['most_profitable_plan']
        assert top['plans_subtype__name'] == plans_subtype_a.name


@pytest.mark.django_db
class TestPersonStatsCompletedAppointmentsKAN167:
    """ /stats-person/ expone completed_appointments = entrenamientos
    realizados = citas cuyo slot ya pasó (slot__date < hoy), no eliminadas."""
    URL = 'stats-person-list'

    def test_cuenta_solo_citas_pasadas_no_eliminadas(self, admin_client, person, slot_past, slot_future):
        from apps.appointments.models import Appointment
        # 1 pasada viva + 1 pasada borrada (soft-delete) + 1 futura
        Appointment.objects.create(person=person, slot=slot_past, reserved=False)
        borrada = Appointment.objects.create(person=person, slot=slot_past, reserved=False)
        borrada.delete()  # soft-delete: no debe contar
        Appointment.objects.create(person=person, slot=slot_future, reserved=False)

        resp = admin_client.get(reverse(self.URL), {'person': person.id})
        assert resp.status_code == 200
        assert resp.data['completed_appointments'] == 1   # solo la pasada viva
        assert resp.data['upcoming_appointments'] == 1    # la futura
        assert resp.data['total_appointments'] == 2       # las 2 vivas

    def test_sin_citas_pasadas_devuelve_cero(self, admin_client, person, slot_future):
        from apps.appointments.models import Appointment
        Appointment.objects.create(person=person, slot=slot_future, reserved=False)
        resp = admin_client.get(reverse(self.URL), {'person': person.id})
        assert resp.status_code == 200
        assert resp.data['completed_appointments'] == 0


@pytest.mark.django_db
class TestStudioFilterKAN148:
    """Los endpoints estadísticos aceptan un 'studio' opcional y las métricas
    cambian según el estudio; sin él se comportan como antes."""

    @pytest.fixture
    def studio_b(self, db):
        from apps.studios.models import Studio
        return Studio.objects.create(name='Studio B')

    @pytest.fixture
    def room_b(self, studio_b):
        from apps.rooms.models import Room
        return Room.objects.create(name='Sala B', studio=studio_b)

    def _pay(self, person, studio, amount):
        return Payment.objects.create(
            person=person, amount=amount, date=timezone.now(), method='Efectivo', studio=studio)

    def _exp(self, studio, amount, etype=None):
        from apps.expenses.models import Expense
        return Expense.objects.create(amount=amount, studio=studio, type=etype)

    def _slot(self, room, start, activity_subtype=None):
        from apps.slots.models import Slot
        return Slot.objects.create(
            room=room, date=date.today(), start_time=start,
            end_time=time(start.hour + 1, 0), availability=10,
            activity_subtype=activity_subtype,
        )

    def _today(self):
        return date.today().isoformat()

    # Financieros
    def test_gross_margin_filtra_por_estudio(self, admin_client, person, studio, studio_b):
        self._pay(person, studio, '100'); self._pay(person, studio_b, '999')
        self._exp(studio, '10'); self._exp(studio_b, '500')
        resp = admin_client.get(reverse('margen-bruto-list'),
                                 {'start_date': self._today(), 'end_date': self._today(), 'studio': studio.id})
        assert resp.status_code == 200
        assert resp.data['total_income'] == 100.0
        assert resp.data['total_expenses'] == 10.0
        assert resp.data['gross_margin'] == 90.0

    def test_gross_margin_studio_invalido_400(self, admin_client):
        resp = admin_client.get(reverse('margen-bruto-list'),
                                 {'start_date': self._today(), 'end_date': self._today(), 'studio': 'abc'})
        assert resp.status_code == 400

    def test_net_margin_filtra_por_estudio(self, admin_client, person, studio, studio_b):
        from apps.expense_type.models import ExpenseType
        sueldo = ExpenseType.objects.create(name='Sueldo')
        self._pay(person, studio, '200'); self._pay(person, studio_b, '999')
        self._exp(studio, '50', sueldo); self._exp(studio_b, '999', sueldo)
        resp = admin_client.get(reverse('margen-neto-list'),
                                 {'start_date': self._today(), 'end_date': self._today(), 'studio': studio.id})
        assert resp.status_code == 200
        assert resp.data['total_income'] == 200.0
        assert resp.data['total_salaries'] == 50.0
        assert resp.data['net_margin'] == 150.0

    def test_expenses_by_type_filtra_por_estudio(self, admin_client, studio, studio_b):
        from apps.expense_type.models import ExpenseType
        t = ExpenseType.objects.create(name='Limpieza')
        self._exp(studio, '30', t); self._exp(studio_b, '999', t)
        resp = admin_client.get(reverse('total-expenses-by-type-list'),
                                 {'start_date': self._today(), 'end_date': self._today(), 'studio': studio.id})
        assert resp.status_code == 200
        row = next(r for r in resp.data if r['expense_type'] == 'Limpieza')
        assert row['total_expenses'] == 30.0

    def test_most_profitable_filtra_por_estudio(self, admin_client, person, studio, studio_b, plans_subtype_a):
        pa = self._pay(person, studio, '100'); pb = self._pay(person, studio_b, '999')
        PaymentItem.objects.create(payment=pa, person=person, plans_subtype=plans_subtype_a,
                                   base_amount='100.00', discount_pct='0')
        PaymentItem.objects.create(payment=pb, person=person, plans_subtype=plans_subtype_a,
                                   base_amount='999.00', discount_pct='0')
        resp = admin_client.get(reverse('most-profitable-plan-list'),
                                 {'year': str(timezone.now().year), 'studio': studio.id})
        assert resp.status_code == 200
        assert float(resp.data['most_profitable_plan']['total_income']) == 100.0

    def test_payment_status_filtra_por_estudio(self, admin_client, person, studio, studio_b):
        self._pay(person, studio_b, '100')  # pagó en B
        resp_a = admin_client.get(reverse('payment-status-current-month-list'), {'studio': studio.id})
        assert resp_a.status_code == 200
        assert resp_a.data['people_who_paid_count'] == 0
        resp_b = admin_client.get(reverse('payment-status-current-month-list'), {'studio': studio_b.id})
        assert resp_b.data['people_who_paid_count'] == 1

    # Basados en appointments/slots
    def test_activity_subtype_filtra_por_estudio(self, admin_client, person, studio, room, room_b, activity_subtype):
        from apps.appointments.models import Appointment
        Appointment.objects.create(person=person, slot=self._slot(room, time(9, 0), activity_subtype))
        Appointment.objects.create(person=person, slot=self._slot(room_b, time(11, 0), activity_subtype))
        resp = admin_client.get(reverse('stats-activity-subtype-list'), {'studio': studio.id})
        assert resp.status_code == 200
        assert sum(r['total_appointments'] for r in resp.data) == 1

    def test_peak_hours_filtra_por_estudio(self, admin_client, person, studio, room, room_b):
        from apps.waiting_list.models import WaitingList
        WaitingList.objects.create(person=person, slot=self._slot(room, time(9, 0)))
        WaitingList.objects.create(person=person, slot=self._slot(room_b, time(11, 0)))
        resp = admin_client.get(reverse('peak-hours-list'), {'studio': studio.id})
        assert resp.status_code == 200
        assert sum(r['total_waiting'] for r in resp.data) == 1

    def test_average_age_by_hour_filtra_por_estudio(self, admin_client, person, studio, room, room_b):
        from apps.appointments.models import Appointment
        person.birth_date = date(1990, 1, 1); person.save(update_fields=['birth_date'])
        Appointment.objects.create(person=person, slot=self._slot(room, time(9, 0)))
        Appointment.objects.create(person=person, slot=self._slot(room_b, time(11, 0)))
        resp = admin_client.get(reverse('average-age-by-hour-list'), {'studio': studio.id})
        assert resp.status_code == 200
        assert len(resp.data) == 1  # solo el horario del estudio A

    def test_sin_studio_incluye_todos(self, admin_client, person, studio, studio_b):
        # Sin el param 'studio', el comportamiento es como antes (todos los estudios).
        self._pay(person, studio, '100'); self._pay(person, studio_b, '50')
        resp = admin_client.get(reverse('margen-bruto-list'),
                                 {'start_date': self._today(), 'end_date': self._today()})
        assert resp.status_code == 200
        assert resp.data['total_income'] == 150.0  # 100 + 50 (ambos estudios)


# /cancellation-rate/ = reservas (Appointment) canceladas

@pytest.mark.django_db
class TestCancellationRateReservasKAN286:
    """El endpoint pasa de contar Personas eliminadas a contar RESERVAS
    (Appointment) canceladas en el período, con anticipación, efecto sobre el
    saldo y reubicaciones aparte."""
    URL = 'cancellation-rate-list'

    def _setup(self, room, person, plans_subtype_a=None):
        from datetime import datetime, timedelta
        from apps.slots.models import Slot
        from apps.appointments.models import Appointment
        slot_date = timezone.now().date().replace(day=15)
        slot_dt = timezone.make_aware(datetime.combine(slot_date, time(10, 0)))

        def mk_slot():
            return Slot.objects.create(room=room, date=slot_date, start_time=time(10, 0),
                                       end_time=time(11, 0), availability=10)
        # 2 vivas
        Appointment.objects.create(slot=mk_slot(), person=person)
        Appointment.objects.create(slot=mk_slot(), person=person)
        # 2 canceladas (deleted seteado): una >24h (con sesión devuelta), una <2h
        cp = None
        if plans_subtype_a is not None:
            cp = PersonActivePlan.objects.create(
                person=person, plans_subtype=plans_subtype_a,
                exp_date=slot_date, sessions_total=8, sessions_remaining=8)
        a1 = Appointment.objects.create(slot=mk_slot(), person=person, consumed_plan=cp)
        a1.deleted = slot_dt - timedelta(hours=30)
        a1.save()
        a2 = Appointment.objects.create(slot=mk_slot(), person=person)
        a2.deleted = slot_dt - timedelta(hours=1)
        a2.save()
        return slot_date

    def test_tasa_y_conteos(self, admin_client, person, room, plans_subtype_a):
        slot_date = self._setup(room, person, plans_subtype_a)
        resp = admin_client.get(reverse(self.URL), {'month': slot_date.strftime('%Y-%m')})
        assert resp.status_code == 200
        d = resp.data
        assert d['total_reservations'] == 4
        assert d['cancelled_reservations'] == 2
        assert d['cancellation_rate'] == 50.0
        assert d['sessions_returned'] == 1

    def test_anticipacion_buckets(self, admin_client, person, room, plans_subtype_a):
        slot_date = self._setup(room, person, plans_subtype_a)
        resp = admin_client.get(reverse(self.URL), {'month': slot_date.strftime('%Y-%m')})
        b = resp.data['anticipation']['buckets']
        assert b == {'lt_2h': 1, 'h2_24': 0, 'gt_24h': 1}
        assert resp.data['anticipation']['average_hours'] == pytest.approx(15.5, abs=0.1)

    def test_reasignaciones_no_cuentan_como_canceladas(self, admin_client, person, room):
        from apps.slots.models import Slot
        from apps.appointments.models import Appointment
        slot_date = timezone.now().date().replace(day=15)
        s1 = Slot.objects.create(room=room, date=slot_date, start_time=time(9, 0),
                                 end_time=time(10, 0), availability=10)
        s2 = Slot.objects.create(room=room, date=slot_date, start_time=time(11, 0),
                                 end_time=time(12, 0), availability=10)
        appt = Appointment.objects.create(slot=s1, person=person)
        # "reubicación": se cambia el slot en el lugar, SIN setear deleted
        appt.slot = s2
        appt.save()
        resp = admin_client.get(reverse(self.URL), {'month': slot_date.strftime('%Y-%m')})
        assert resp.data['cancelled_reservations'] == 0
        assert resp.data['total_reservations'] == 1
        assert resp.data['reassignments'] == 0

    def test_filtra_por_estudio(self, admin_client, person, room):
        from apps.rooms.models import Room
        from apps.studios.models import Studio
        from apps.slots.models import Slot
        from apps.appointments.models import Appointment
        slot_date = timezone.now().date().replace(day=15)
        # cancelada en estudio A (room.studio)
        sa = Slot.objects.create(room=room, date=slot_date, start_time=time(9, 0),
                                 end_time=time(10, 0), availability=10)
        aa = Appointment.objects.create(slot=sa, person=person); aa.deleted = timezone.now(); aa.save()
        # cancelada en estudio B
        studio_b = Studio.objects.create(name='Studio B')
        room_b = Room.objects.create(name='Sala B', studio=studio_b)
        sb = Slot.objects.create(room=room_b, date=slot_date, start_time=time(9, 0),
                                 end_time=time(10, 0), availability=10)
        ab = Appointment.objects.create(slot=sb, person=person); ab.deleted = timezone.now(); ab.save()
        resp = admin_client.get(reverse(self.URL),
                                {'month': slot_date.strftime('%Y-%m'), 'studio': room.studio_id})
        assert resp.data['total_reservations'] == 1
        assert resp.data['cancelled_reservations'] == 1

    def test_month_requerido_400(self, admin_client):
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 400

    def test_sin_reservas_rate_cero(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'month': '2099-01'})
        assert resp.status_code == 200
        assert resp.data['total_reservations'] == 0
        assert resp.data['cancellation_rate'] == 0


# /occupancy-by-hour/ = ocupación por franja

@pytest.mark.django_db
class TestOccupancyByHourKAN286:
    """Ocupación agrupada por estudio/sala/actividad/día/hora. Ocupación =
    reservas confirmadas ÷ cupos (availability remanente + confirmadas)."""
    URL = 'occupancy-by-hour-list'

    def _monday(self):
        from datetime import timedelta
        d = date(2099, 1, 1)
        while d.weekday() != 0:
            d += timedelta(days=1)
        return d

    def _slot(self, room, d, start, availability, activity_subtype=None):
        from apps.slots.models import Slot
        return Slot.objects.create(room=room, date=d, start_time=start,
                                   end_time=time(start.hour + 1, 0),
                                   availability=availability,
                                   activity_subtype=activity_subtype)

    def _appts(self, slot, person, alive=0, cancelled=0):
        from apps.appointments.models import Appointment
        for _ in range(alive):
            Appointment.objects.create(slot=slot, person=person)
        for _ in range(cancelled):
            a = Appointment.objects.create(slot=slot, person=person)
            a.deleted = timezone.now(); a.save()

    def test_grouping_and_occupancy(self, admin_client, person, room, activity_subtype):
        mon = self._monday()
        # slot1: availability=1, 3 vivas + 1 cancelada -> confirmadas=3, cupos=4
        s1 = self._slot(room, mon, time(10, 0), 1, activity_subtype)
        self._appts(s1, person, alive=3, cancelled=1)
        # slot2 (misma sala/hora/actividad/día): availability=0, 4 vivas -> cupos=4, lleno
        s2 = self._slot(room, mon, time(10, 0), 0, activity_subtype)
        self._appts(s2, person, alive=4)
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        assert len(resp.data) == 1
        row = resp.data[0]
        assert row['studio_id'] == room.studio_id
        assert row['room_id'] == room.id
        assert row['activity_subtype_id'] == activity_subtype.id
        assert row['weekday'] == 0
        assert row['weekday_name'] == 'Lunes'
        assert row['classes'] == 2
        assert row['total_reservations'] == 7
        assert row['total_cupos'] == 8
        assert row['occupancy_pct'] == 87.5
        assert row['full_classes_pct'] == 50.0

    def test_filtra_por_estudio(self, admin_client, person, room):
        from apps.rooms.models import Room
        from apps.studios.models import Studio
        mon = self._monday()
        s_a = self._slot(room, mon, time(9, 0), 2); self._appts(s_a, person, alive=1)
        studio_b = Studio.objects.create(name='Studio B')
        room_b = Room.objects.create(name='Sala B', studio=studio_b)
        s_b = self._slot(room_b, mon, time(9, 0), 2); self._appts(s_b, person, alive=1)
        resp = admin_client.get(reverse(self.URL), {'studio': room.studio_id})
        assert len(resp.data) == 1
        assert resp.data[0]['studio_id'] == room.studio_id

    def test_date_range_filter(self, admin_client, person, room):
        from datetime import timedelta
        mon = self._monday()
        s_in = self._slot(room, mon, time(9, 0), 2); self._appts(s_in, person, alive=1)
        s_out = self._slot(room, mon + timedelta(days=30), time(9, 0), 2); self._appts(s_out, person, alive=1)
        resp = admin_client.get(reverse(self.URL),
                                {'start_date': mon.isoformat(), 'end_date': mon.isoformat()})
        assert len(resp.data) == 1

    def test_empty_returns_list(self, admin_client):
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        assert resp.data == []


# /retention-rate/ = renovaciones de planes

@pytest.mark.django_db
class TestRenewalRateKAN286:
    """El endpoint pasa de 'pagó >1 vez' a RENOVACIONES: un plan se considera
    renovado si el siguiente plan contratado del mismo alumno+actividad cae dentro
    de exp_date + window_days. Tasa sobre los planes cuyo plazo ya venció."""
    URL = 'retention-rate-list'

    def _plan(self, person, subtype, exp_offset, created_offset):
        from apps.people.models import PersonActivePlan
        from datetime import timedelta
        today = timezone.now().date()
        p = PersonActivePlan.objects.create(
            person=person, plans_subtype=subtype,
            exp_date=today + timedelta(days=exp_offset),
            sessions_total=8, sessions_remaining=8,
        )
        # created_at es auto_now_add -> se fija con update() para controlar el test
        PersonActivePlan.objects.filter(pk=p.pk).update(
            created_at=timezone.make_aware(
                __import__('datetime').datetime.combine(today + timedelta(days=created_offset),
                                                        time(12, 0)))
        )
        return p

    def _person(self, dni):
        from apps.people.models import Person
        return Person.objects.create(name='N', last_name='A', dni=dni)

    def test_tasa_renovacion(self, admin_client, plans_subtype_a):
        p1 = self._person('80000001')
        # P: vencido hace rato, plazo ya cumplido (exp -60 -> +30 < hoy). Elegible.
        self._plan(p1, plans_subtype_a, exp_offset=-60, created_offset=-120)
        # Q: siguiente plan del mismo alumno+actividad, contratado -50 (dentro de -60+30=-30). Renueva a P.
        self._plan(p1, plans_subtype_a, exp_offset=-10, created_offset=-50)
        # R: otro alumno, vencido, sin siguiente -> elegible, no renovado
        p2 = self._person('80000002')
        self._plan(p2, plans_subtype_a, exp_offset=-60, created_offset=-120)
        # S: plazo NO cumplido (exp -5 -> +30 > hoy) -> no elegible
        p3 = self._person('80000003')
        self._plan(p3, plans_subtype_a, exp_offset=-5, created_offset=-20)

        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        assert resp.data['window_days'] == 30
        assert resp.data['eligible_plans'] == 2   # P y R (S excluido)
        assert resp.data['renewed_plans'] == 1    # P
        assert resp.data['renewal_rate'] == 50.0

    def test_window_configurable(self, admin_client, plans_subtype_a):
        p1 = self._person('80000010')
        # P vencido hace mucho (exp -100) -> elegible con window 30 y 60.
        self._plan(p1, plans_subtype_a, exp_offset=-100, created_offset=-120)
        # Q contratado -60 -> gap vs P.exp_date (-100) = 40 días.
        self._plan(p1, plans_subtype_a, exp_offset=-5, created_offset=-60)
        # window=30: gap 40 > 30 -> no renueva
        r30 = admin_client.get(reverse(self.URL), {'window_days': 30})
        assert r30.data['renewed_plans'] == 0
        # window=60: gap 40 <= 60 -> renueva
        r60 = admin_client.get(reverse(self.URL), {'window_days': 60})
        assert r60.data['renewed_plans'] == 1

    def test_sin_planes_rate_cero(self, admin_client):
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        assert resp.data['eligible_plans'] == 0
        assert resp.data['renewal_rate'] == 0

    def test_window_invalido_400(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'window_days': 'abc'})
        assert resp.status_code == 400


# /plan-validity/ = vigencia de planes

@pytest.mark.django_db
class TestPlanValidityKAN286:
    """Clasifica PersonActivePlan por vigencia según exp_date (NO por si pagó en
    el mes): vigentes, vencidos, próximos a vencer (days_ahead) y agotados."""
    URL = 'plan-validity-list'

    def _plan(self, person, subtype, exp_offset, remaining=5):
        from apps.people.models import PersonActivePlan
        from datetime import timedelta
        return PersonActivePlan.objects.create(
            person=person, plans_subtype=subtype,
            exp_date=timezone.now().date() + timedelta(days=exp_offset),
            sessions_total=8, sessions_remaining=remaining,
        )

    def _person(self, dni):
        from apps.people.models import Person
        return Person.objects.create(name='N', last_name='A', dni=dni)

    def test_clasifica_vigencia(self, admin_client, plans_subtype_a):
        self._plan(self._person('81000001'), plans_subtype_a, exp_offset=30)    # vigente
        self._plan(self._person('81000002'), plans_subtype_a, exp_offset=3)     # vigente + próximo (<=7)
        self._plan(self._person('81000003'), plans_subtype_a, exp_offset=-5)    # vencido por fecha
        self._plan(self._person('81000004'), plans_subtype_a, exp_offset=10, remaining=0)  # vigente por fecha pero agotado
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        d = resp.data
        assert d['days_ahead'] == 7
        assert d['active'] == 3          # exp_date >= hoy (incluye el agotado)
        assert d['expired'] == 1         # exp_date < hoy
        assert d['expiring_soon'] == 1   # vigente y exp_date <= hoy+7
        assert d['sessions_exhausted'] == 1  # vigente por fecha pero sin sesiones

    def test_days_ahead_configurable(self, admin_client, plans_subtype_a):
        self._plan(self._person('81000010'), plans_subtype_a, exp_offset=20)
        assert admin_client.get(reverse(self.URL), {'days_ahead': 7}).data['expiring_soon'] == 0
        assert admin_client.get(reverse(self.URL), {'days_ahead': 30}).data['expiring_soon'] == 1

    def test_days_ahead_invalido_400(self, admin_client):
        assert admin_client.get(reverse(self.URL), {'days_ahead': 'x'}).status_code == 400

    def test_sin_planes(self, admin_client):
        d = admin_client.get(reverse(self.URL)).data
        assert d['active'] == 0 and d['expired'] == 0


# /waiting-list-stats/ = solicitudes de lista de espera

@pytest.mark.django_db
class TestWaitingListStatsKAN286:
    """Agrupa solicitudes de lista de espera por horario y cuántas terminaron en
    reserva. Dedup por (persona, clase); vínculo con reserva vía Appointment."""
    URL = 'waiting-list-stats-list'

    def _slot(self, room, start):
        from apps.slots.models import Slot
        return Slot.objects.create(room=room, date=timezone.now().date(), start_time=start,
                                   end_time=time(start.hour + 1, 0), availability=10)

    def test_agrupa_y_conversion(self, admin_client, person, room):
        from apps.people.models import Person
        from apps.waiting_list.models import WaitingList
        from apps.appointments.models import Appointment
        s = self._slot(room, time(10, 0))
        p2 = Person.objects.create(name='B', last_name='B', dni='82000002')
        # person: solicita (dup x2 -> cuenta 1) y termina en reserva
        WaitingList.objects.create(person=person, slot=s)
        WaitingList.objects.create(person=person, slot=s)
        Appointment.objects.create(person=person, slot=s)
        # p2: solicita y NO reserva
        WaitingList.objects.create(person=p2, slot=s)
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        row = [r for r in resp.data if r['start_time'] == '10:00:00'][0]
        assert row['total_requests'] == 2   # person (dedup) + p2
        assert row['converted'] == 1        # solo person
        assert row['conversion_rate'] == 50.0

    def test_filtra_por_estudio(self, admin_client, person, room):
        from apps.rooms.models import Room
        from apps.studios.models import Studio
        from apps.waiting_list.models import WaitingList
        WaitingList.objects.create(person=person, slot=self._slot(room, time(9, 0)))
        studio_b = Studio.objects.create(name='Studio B')
        room_b = Room.objects.create(name='Sala B', studio=studio_b)
        WaitingList.objects.create(person=person, slot=self._slot(room_b, time(9, 0)))
        resp = admin_client.get(reverse(self.URL), {'studio': room.studio_id})
        assert sum(r['total_requests'] for r in resp.data) == 1

    def test_vacio(self, admin_client):
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200 and resp.data == []


# /status-clients/ con filtros estudio/actividad/plan

@pytest.mark.django_db
class TestClientsStatusFiltersKAN286:
    URL = 'status-clients-list'

    def test_sin_filtros_cuenta_todos(self, admin_client, person):
        from apps.people.models import Person
        Person.objects.create(name='X', last_name='Y', dni='83000001', deleted=timezone.now())
        d = admin_client.get(reverse(self.URL)).data
        assert d['total_active_clients'] == 1
        assert d['total_inactive_clients'] == 1

    def test_filtro_plan_y_actividad_sin_doble_conteo(self, admin_client, person, plans_subtype_a):
        from apps.people.models import PersonActivePlan
        from datetime import timedelta
        exp = timezone.now().date() + timedelta(days=10)
        # dos planes del MISMO alumno+actividad -> debe contar 1
        PersonActivePlan.objects.create(person=person, plans_subtype=plans_subtype_a,
                                        exp_date=exp, sessions_total=8, sessions_remaining=8)
        PersonActivePlan.objects.create(person=person, plans_subtype=plans_subtype_a,
                                        exp_date=exp, sessions_total=8, sessions_remaining=8)
        d = admin_client.get(reverse(self.URL),
                             {'plan': plans_subtype_a.id,
                              'activity': plans_subtype_a.activity_subtype_id}).data
        assert d['total_active_clients'] == 1

    def test_filtro_estudio(self, admin_client, person, room):
        from apps.rooms.models import Room
        from apps.studios.models import Studio
        from apps.slots.models import Slot
        from apps.appointments.models import Appointment
        from apps.people.models import Person
        s = Slot.objects.create(room=room, date=timezone.now().date(), start_time=time(9, 0),
                                end_time=time(10, 0), availability=10)
        Appointment.objects.create(person=person, slot=s)
        # otra persona con turno en estudio B
        p2 = Person.objects.create(name='B', last_name='B', dni='83000010')
        studio_b = Studio.objects.create(name='Studio B')
        room_b = Room.objects.create(name='Sala B', studio=studio_b)
        s2 = Slot.objects.create(room=room_b, date=timezone.now().date(), start_time=time(9, 0),
                                 end_time=time(10, 0), availability=10)
        Appointment.objects.create(person=p2, slot=s2)
        d = admin_client.get(reverse(self.URL), {'studio': room.studio_id}).data
        assert d['total_active_clients'] == 1

    def test_filtro_invalido_400(self, admin_client):
        assert admin_client.get(reverse(self.URL), {'activity': 'x'}).status_code == 400


# /average-age/ con rangos + filtros

@pytest.mark.django_db
class TestAverageAgeRangesKAN286:
    URL = 'average-age-list'

    def _person(self, dni, birth_year):
        from apps.people.models import Person
        return Person.objects.create(name='N', last_name='A', dni=dni, birth_date=date(birth_year, 6, 15))

    def test_promedio_y_rangos(self, admin_client):
        self._person('84000001', timezone.now().year - 10)  # 10 -> <18
        self._person('84000002', timezone.now().year - 25)  # 25 -> 18-29
        self._person('84000003', timezone.now().year - 40)  # 40 -> 30-44
        d = admin_client.get(reverse(self.URL)).data
        assert d['average_age'] == pytest.approx((10 + 25 + 40) / 3, abs=0.6)
        assert d['total'] == 3
        buckets = d['ranges']
        assert buckets['<18'] == 1
        assert buckets['18-29'] == 1
        assert buckets['30-44'] == 1
        assert buckets['45-59'] == 0
        assert buckets['60+'] == 0

    def test_filtro_estudio(self, admin_client, person, room):
        from apps.rooms.models import Room
        from apps.studios.models import Studio
        from apps.slots.models import Slot
        from apps.appointments.models import Appointment
        person.birth_date = date(timezone.now().year - 30, 1, 1); person.save()
        s = Slot.objects.create(room=room, date=timezone.now().date(), start_time=time(9, 0),
                                end_time=time(10, 0), availability=10)
        Appointment.objects.create(person=person, slot=s)
        p2 = self._person('84000010', timezone.now().year - 50)
        studio_b = Studio.objects.create(name='Studio B')
        room_b = Room.objects.create(name='Sala B', studio=studio_b)
        s2 = Slot.objects.create(room=room_b, date=timezone.now().date(), start_time=time(9, 0),
                                 end_time=time(10, 0), availability=10)
        Appointment.objects.create(person=p2, slot=s2)
        d = admin_client.get(reverse(self.URL), {'studio': room.studio_id}).data
        assert d['total'] == 1

    def test_sin_personas(self, admin_client):
        d = admin_client.get(reverse(self.URL)).data
        assert d['total'] == 0 and d['average_age'] is None


# /most-profitable-plan/ ranking completo

@pytest.mark.django_db
class TestMostProfitableRankingKAN286:
    URL = 'most-profitable-plan-list'

    def test_devuelve_ranking(self, admin_client, person, plans_subtype_a, activity_subtype, studio):
        from apps.plans_type.models import PlansType
        from apps.plans_subtype.models import PlansSubtype
        from apps.payments.models import Payment, PaymentItem
        ptype = PlansType.objects.create(name='T2')
        sub_b = PlansSubtype.objects.create(name='Sub B', plan_type=ptype, activity_subtype=activity_subtype)
        year = timezone.now().year
        pay = Payment.objects.create(person=person, amount='300', date=timezone.now(), method='Efectivo', studio=studio)
        PaymentItem.objects.create(payment=pay, person=person, plans_subtype=plans_subtype_a,
                                   base_amount=200, final_amount=200)
        PaymentItem.objects.create(payment=pay, person=person, plans_subtype=sub_b,
                                   base_amount=100, final_amount=100)
        d = admin_client.get(reverse(self.URL), {'year': str(year)}).data
        assert 'ranking' in d
        assert len(d['ranking']) == 2
        # ordenado por ingresos desc
        assert d['ranking'][0]['total_income'] >= d['ranking'][1]['total_income']
        assert d['most_profitable_plan'] == d['ranking'][0]


# /total-expenses-by-type/ filtro categoría

@pytest.mark.django_db
class TestExpensesByTypeCategoryKAN286:
    URL = 'total-expenses-by-type-list'

    def test_filtro_categoria(self, admin_client, studio):
        from apps.expense_type.models import ExpenseType
        from apps.expenses.models import Expense
        t1 = ExpenseType.objects.create(name='Sueldos')
        t2 = ExpenseType.objects.create(name='Insumos')
        Expense.objects.create(amount='100', studio=studio, type=t1, date=timezone.now())
        Expense.objects.create(amount='50', studio=studio, type=t2, date=timezone.now())
        today = timezone.now().date().isoformat()
        d = admin_client.get(reverse(self.URL),
                             {'start_date': today, 'end_date': today, 'expense_type': t1.id}).data
        assert len(d) == 1
        assert d[0]['expense_type'] == 'Sueldos'
        assert d[0]['total_expenses'] == 100

    def test_categoria_invalida_400(self, admin_client):
        today = timezone.now().date().isoformat()
        resp = admin_client.get(reverse(self.URL),
                                {'start_date': today, 'end_date': today, 'expense_type': 'x'})
        assert resp.status_code == 400


# /payments-breakdown/ medio de pago + concepto

@pytest.mark.django_db
class TestPaymentsBreakdownKAN286:
    URL = 'payments-breakdown-list'

    def test_desglose(self, admin_client, person, plans_subtype_a, studio):
        from apps.payments.models import Payment, PaymentItem
        pay1 = Payment.objects.create(person=person, amount='200', date=timezone.now(),
                                      method='Efectivo', studio=studio)
        PaymentItem.objects.create(payment=pay1, person=person, plans_subtype=plans_subtype_a,
                                   base_amount=200, final_amount=200)
        pay2 = Payment.objects.create(person=person, amount='100', date=timezone.now(),
                                      method='Transferencia', studio=studio)
        PaymentItem.objects.create(payment=pay2, person=person, plans_subtype=plans_subtype_a,
                                   base_amount=100, final_amount=100)
        d = admin_client.get(reverse(self.URL), {'studio': studio.id}).data
        assert d['total_income'] == 300
        methods = {r['method']: r['total'] for r in d['by_method']}
        assert methods == {'Efectivo': 200, 'Transferencia': 100}
        concepts = {r['plans_subtype']: r['total'] for r in d['by_concept']}
        assert concepts[plans_subtype_a.name] == 300

    def test_filtra_por_estudio(self, admin_client, person, plans_subtype_a, studio):
        from apps.rooms.models import Room
        from apps.studios.models import Studio
        from apps.payments.models import Payment
        Payment.objects.create(person=person, amount='200', date=timezone.now(), method='Efectivo', studio=studio)
        studio_b = Studio.objects.create(name='Studio B')
        Payment.objects.create(person=person, amount='999', date=timezone.now(), method='Efectivo', studio=studio_b)
        d = admin_client.get(reverse(self.URL), {'studio': studio.id}).data
        assert d['total_income'] == 200


# /classes-and-reservations/

@pytest.mark.django_db
class TestClassesAndReservationsKAN286:
    URL = 'classes-and-reservations-list'

    def test_conteos_por_estado(self, admin_client, person, room, activity_subtype):
        from apps.slots.models import Slot
        from apps.appointments.models import Appointment
        s1 = Slot.objects.create(room=room, date=timezone.now().date(), start_time=time(9, 0),
                                 end_time=time(10, 0), availability=10, activity_subtype=activity_subtype)
        s2 = Slot.objects.create(room=room, date=timezone.now().date(), start_time=time(10, 0),
                                 end_time=time(11, 0), availability=10, activity_subtype=activity_subtype)
        Appointment.objects.create(person=person, slot=s1)           # activa
        a = Appointment.objects.create(person=person, slot=s2)       # cancelada
        a.deleted = timezone.now(); a.save()
        d = admin_client.get(reverse(self.URL)).data
        assert d['total_classes'] == 2
        assert d['reservations_active'] == 1
        assert d['reservations_cancelled'] == 1
        assert d['by_activity'][0]['classes'] == 2

    def test_filtra_por_estudio(self, admin_client, room):
        from apps.rooms.models import Room
        from apps.studios.models import Studio
        from apps.slots.models import Slot
        Slot.objects.create(room=room, date=timezone.now().date(), start_time=time(9, 0),
                            end_time=time(10, 0), availability=10)
        studio_b = Studio.objects.create(name='Studio B')
        room_b = Room.objects.create(name='Sala B', studio=studio_b)
        Slot.objects.create(room=room_b, date=timezone.now().date(), start_time=time(9, 0),
                            end_time=time(10, 0), availability=10)
        d = admin_client.get(reverse(self.URL), {'studio': room.studio_id}).data
        assert d['total_classes'] == 1


# /#11/#13/#6/#4: nuevos endpoints

@pytest.mark.django_db
class TestPlanUsageKAN286:
    URL = 'plan-usage-list'

    def test_uso(self, admin_client, person, plans_subtype_a):
        from apps.people.models import PersonActivePlan
        from datetime import timedelta
        today = timezone.now().date()
        # vigente: 8 total, 3 restantes -> 5 consumidas
        PersonActivePlan.objects.create(person=person, plans_subtype=plans_subtype_a,
                                        exp_date=today + timedelta(days=10), sessions_total=8, sessions_remaining=3)
        # vencido con 2 sin usar
        PersonActivePlan.objects.create(person=person, plans_subtype=plans_subtype_a,
                                        exp_date=today - timedelta(days=5), sessions_total=8, sessions_remaining=2)
        d = admin_client.get(reverse(self.URL)).data
        assert d['total_sessions'] == 16
        assert d['consumed_sessions'] == 11   # (8-3)+(8-2)
        assert d['remaining_sessions'] == 5
        assert d['unused_at_expiry'] == 2


@pytest.mark.django_db
class TestOccupancyRateKAN286:
    URL = 'occupancy-rate-list'

    def test_total(self, admin_client, person, room):
        from apps.slots.models import Slot
        from apps.appointments.models import Appointment
        s1 = Slot.objects.create(room=room, date=timezone.now().date(), start_time=time(9, 0),
                                 end_time=time(10, 0), availability=1)
        Appointment.objects.create(person=person, slot=s1)  # confirmed 1, cupos 2
        s2 = Slot.objects.create(room=room, date=timezone.now().date(), start_time=time(10, 0),
                                 end_time=time(11, 0), availability=0)
        Appointment.objects.create(person=person, slot=s2)  # confirmed 1, cupos 1, lleno
        d = admin_client.get(reverse(self.URL)).data
        assert d['total_classes'] == 2
        assert d['total_reservations'] == 2
        assert d['total_cupos'] == 3
        assert d['occupancy_pct'] == pytest.approx(66.67, abs=0.1)
        assert d['full_classes'] == 1


@pytest.mark.django_db
class TestOccupancyEvolutionKAN286:
    URL = 'occupancy-evolution-list'

    def test_por_mes(self, admin_client, person, room):
        from apps.slots.models import Slot
        from apps.appointments.models import Appointment
        s = Slot.objects.create(room=room, date=timezone.now().date().replace(day=15),
                                start_time=time(9, 0), end_time=time(10, 0), availability=1)
        Appointment.objects.create(person=person, slot=s)
        d = admin_client.get(reverse(self.URL)).data
        assert len(d) == 1
        assert d[0]['period'] == timezone.now().date().strftime('%Y-%m')
        assert d[0]['total_reservations'] == 1
        assert d[0]['total_cupos'] == 2


@pytest.mark.django_db
class TestTenureKAN286:
    URL = 'tenure-list'

    def test_rangos(self, admin_client, person):
        # person recién creado -> <1m
        d = admin_client.get(reverse(self.URL)).data
        assert d['total'] == 1
        assert d['ranges']['<1m'] == 1


@pytest.mark.django_db
class TestClientsByMonthNetGrowthKAN286:
    URL = 'clients-by-month-list'

    def test_crecimiento_neto_y_bajas(self, admin_client, person):
        from apps.people.models import Person
        # una baja
        Person.objects.create(name='X', last_name='Y', dni='85000001', deleted=timezone.now())
        d = admin_client.get(reverse(self.URL)).data
        assert 'net_growth_by_month' in d
        total_cancel = sum(r['total_cancellations'] for r in d['cancellations_by_month'])
        assert total_cancel == 1
        total_net = sum(r['net_growth'] for r in d['net_growth_by_month'])
        assert total_net == 1   # 2 altas - 1 baja
# filtro por estudio unificado con el helper común

@pytest.mark.django_db
class TestStatsStudioFilterUnificadoKAN148:
    MSG_400 = "El parámetro 'studio' debe ser un número entero positivo."

    def _today(self):
        return timezone.localdate().isoformat()

    def _rango(self, **extra):
        return {'start_date': self._today(), 'end_date': self._today(), **extra}

    def _pay(self, person, studio, amount):
        from apps.payments.models import Payment
        return Payment.objects.create(person=person, amount=amount, date=timezone.now(),
                                      method='Efectivo', studio=studio)

    def _exp(self, studio, amount):
        from apps.expenses.models import Expense
        return Expense.objects.create(amount=amount, studio=studio)

    @pytest.mark.parametrize('value', ['abc', '-1', '', '0'])
    def test_mismo_400_que_los_demas_endpoints(self, admin_client, value):
        resp = admin_client.get(reverse('margen-bruto-list') +
                                f'?start_date={self._today()}&end_date={self._today()}&studio={value}')
        assert resp.status_code == 400
        assert resp.data == {'detail': self.MSG_400}

    @pytest.mark.parametrize('url', ['margen-bruto-list', 'margen-neto-list', 'total-expenses-by-type-list'])
    def test_estudio_inexistente_404(self, admin_client, url):
        resp = admin_client.get(reverse(url), self._rango(studio=999999))
        assert resp.status_code == 404
        assert resp.data == {'detail': 'No existe un estudio con id 999999.'}

    @pytest.mark.parametrize('url', ['peak-hours-list', 'average-age-by-hour-list',
                                     'payment-status-current-month-list', 'stats-activity-subtype-list'])
    def test_estudio_inexistente_404_sin_fechas(self, admin_client, url):
        resp = admin_client.get(reverse(url), {'studio': 999999})
        assert resp.status_code == 404

    def test_varios_estudios_suman(self, admin_client, person, studio, studio_b, empty_studio):
        self._pay(person, studio, '100'); self._pay(person, studio_b, '50')
        self._exp(studio, '10'); self._exp(studio_b, '5')
        url = reverse('margen-bruto-list')
        a = admin_client.get(url, self._rango(studio=studio.id)).data
        b = admin_client.get(url, self._rango(studio=studio_b.id)).data
        ab = admin_client.get(url + f'?start_date={self._today()}&end_date={self._today()}'
                              f'&studio={studio.id},{studio_b.id}').data
        todos = admin_client.get(url, self._rango()).data
        assert a['gross_margin'] == 90.0 and b['gross_margin'] == 45.0
        assert ab['gross_margin'] == todos['gross_margin'] == 135.0

    def test_estudio_sin_datos_200_en_cero(self, admin_client, person, studio, empty_studio):
        self._pay(person, studio, '100')
        resp = admin_client.get(reverse('margen-bruto-list'), self._rango(studio=empty_studio.id))
        assert resp.status_code == 200
        assert resp.data['gross_margin'] == 0 and 'detail' not in resp.data

    def test_estudio_dado_de_baja_objeto_agrega_detail(self, admin_client, person, deleted_studio):
        self._pay(person, deleted_studio, '70')
        resp = admin_client.get(reverse('margen-bruto-list'), self._rango(studio=deleted_studio.id))
        assert resp.status_code == 200
        assert resp.data['total_income'] == 70.0
        assert resp.data['detail'] == f'El estudio con id {deleted_studio.id} está dado de baja.'

    def test_estudio_dado_de_baja_lista_se_envuelve(self, admin_client, deleted_studio):
        resp = admin_client.get(reverse('total-expenses-by-type-list'), self._rango(studio=deleted_studio.id))
        assert resp.status_code == 200
        assert resp.data['detail'] == f'El estudio con id {deleted_studio.id} está dado de baja.'
        assert isinstance(resp.data['results'], list)

    def test_usuario_sin_permiso_403(self, consultor_client, studio):
        # margen-bruto es solo Admin/Super; el filtro no cambia los permisos.
        resp = consultor_client.get(reverse('margen-bruto-list'), self._rango(studio=studio.id))
        assert resp.status_code == 403

    def test_stats_studio_sigue_requiriendo_studio(self, admin_client):
        resp = admin_client.get(reverse('stats-studio-list'))
        assert resp.status_code == 400
        assert resp.data == {'detail': "El parámetro 'studio' es requerido."}

    def test_stats_studio_valida_y_acepta_varios(self, admin_client, person, studio, studio_b):
        self._pay(person, studio, '100'); self._pay(person, studio_b, '50')
        assert admin_client.get(reverse('stats-studio-list'), {'studio': 'abc'}).status_code == 400
        assert admin_client.get(reverse('stats-studio-list'), {'studio': 999999}).status_code == 404
        resp = admin_client.get(reverse('stats-studio-list') + f'?studio={studio.id},{studio_b.id}')
        assert resp.status_code == 200
        assert resp.data['total_income'] == 150.0
        assert resp.data['studio'] == [studio.id, studio_b.id]
        assert resp.data['studio_id'] == f'{studio.id},{studio_b.id}'


# feedback de revisión

def _mk_slot(room, d, start, availability, activity_subtype=None):
    from apps.slots.models import Slot
    return Slot.objects.create(room=room, date=d, start_time=start,
                               end_time=time(start.hour + 1, 0),
                               availability=availability, activity_subtype=activity_subtype)


def _mk_appts(slot, person, n):
    from apps.appointments.models import Appointment
    for _ in range(n):
        Appointment.objects.create(slot=slot, person=person)


@pytest.mark.django_db
class TestFeedbackKAN286:
    def test_retention_excluye_planes_sin_created_at(self, admin_client, person, plans_subtype_a):
        from datetime import timedelta
        p = PersonActivePlan.objects.create(
            person=person, plans_subtype=plans_subtype_a,
            exp_date=timezone.now().date() - timedelta(days=100),
            sessions_total=8, sessions_remaining=8,
        )
        PersonActivePlan.objects.filter(pk=p.pk).update(created_at=None)
        resp = admin_client.get(reverse('retention-rate-list'))
        assert resp.status_code == 200
        assert resp.data['eligible_plans'] == 0

    def test_occupancy_by_hour_recurrencia_alta_y_baja(self, admin_client, person, room):
        d = date(2099, 1, 5)  # lunes
        for av, alive in [(0, 4), (0, 4), (0, 4), (4, 0)]:
            s = _mk_slot(room, d, time(10, 0), av, None)
            _mk_appts(s, person, alive)
        row = admin_client.get(reverse('occupancy-by-hour-list')).data[0]
        assert row['classes'] == 4
        assert row['high_occupancy_recurrence'] == 0.75
        assert row['low_occupancy_recurrence'] == 0.25

    def test_occupancy_evolution_por_franja_y_mes(self, admin_client, person, room):
        # misma franja (lunes 10:00) en dos meses distintos
        s1 = _mk_slot(room, date(2099, 1, 5), time(10, 0), 2)
        _mk_appts(s1, person, 2)   # cupos 4, res 2 -> 50
        s2 = _mk_slot(room, date(2099, 2, 2), time(10, 0), 0)
        _mk_appts(s2, person, 4)   # cupos 4, res 4 -> 100
        d = admin_client.get(reverse('occupancy-evolution-list')).data
        assert len(d) == 2
        assert [r['period'] for r in d] == ['2099-01', '2099-02']
        assert [r['occupancy_pct'] for r in d] == [50.0, 100.0]
        assert d[0]['room_id'] == d[1]['room_id'] == room.id
        assert d[0]['weekday'] == d[1]['weekday'] == 0
        assert d[0]['start_time'] == '10:00:00'
        assert d[0]['weekday_name'] == 'Lunes'

    def test_occupancy_evolution_granularidad_semana(self, admin_client, person, room):
        s1 = _mk_slot(room, date(2099, 1, 5), time(10, 0), 1)
        _mk_appts(s1, person, 1)
        s2 = _mk_slot(room, date(2099, 1, 12), time(10, 0), 1)
        _mk_appts(s2, person, 1)
        d = admin_client.get(reverse('occupancy-evolution-list'), {'granularity': 'week'}).data
        assert [r['period'] for r in d] == ['2099-W02', '2099-W03']
        m = admin_client.get(reverse('occupancy-evolution-list')).data
        assert len(m) == 1 and m[0]['classes'] == 2

    def test_occupancy_evolution_granularidad_invalida(self, admin_client):
        resp = admin_client.get(reverse('occupancy-evolution-list'), {'granularity': 'day'})
        assert resp.status_code == 400

    def test_classes_by_room(self, admin_client, room, room_b):
        d = date(2099, 1, 5)
        _mk_slot(room, d, time(9, 0), 5)
        _mk_slot(room, d, time(10, 0), 5)
        _mk_slot(room_b, d, time(9, 0), 5)
        data = admin_client.get(reverse('classes-and-reservations-list')).data
        by_room = {r['room_id']: r for r in data['by_room']}
        assert by_room[room.id]['classes'] == 2
        assert by_room[room.id]['room_name'] == room.name
        assert by_room[room_b.id]['classes'] == 1
        assert data['total_classes'] == 3

    def test_average_age_filtro_horario(self, admin_client, room):
        from apps.people.models import Person
        from apps.appointments.models import Appointment
        by = date(2099, 1, 5)
        for dni, start in [('85000001', time(10, 0)), ('85000002', time(11, 0))]:
            p = Person.objects.create(name='N' + dni, last_name='A', dni=dni,
                                      birth_date=date(timezone.now().year - 30, 1, 1))
            Appointment.objects.create(person=p, slot=_mk_slot(room, by, start, 5))
        url = reverse('average-age-list')
        assert admin_client.get(url).data['total'] == 2
        assert admin_client.get(url, {'start_time': '10:00'}).data['total'] == 1
        assert admin_client.get(url, {'start_time': '10:00:00'}).data['total'] == 1
        assert admin_client.get(url, {'start_time': 'xx'}).status_code == 400

    def test_net_margin_fecha_invalida_trae_detail(self, admin_client):
        resp = admin_client.get(reverse('margen-neto-list'),
                                {'start_date': 'bad', 'end_date': 'bad'})
        assert resp.status_code == 400
        assert 'detail' in resp.data

    def test_average_age_studio_y_horario_misma_cita(self, admin_client, room, room_b):
        from apps.people.models import Person
        from apps.appointments.models import Appointment
        d = date(2099, 1, 5)
        bd = date(timezone.now().year - 30, 1, 1)
        # cruzada: estudio A a las 11:00 y estudio B a las 10:00 -> NO debe matchear A+10:00
        cross = Person.objects.create(name='Cruz', last_name='A', dni='86000001', birth_date=bd)
        Appointment.objects.create(person=cross, slot=_mk_slot(room, d, time(11, 0), 5))
        Appointment.objects.create(person=cross, slot=_mk_slot(room_b, d, time(10, 0), 5))
        ok = Person.objects.create(name='Ok', last_name='A', dni='86000002', birth_date=bd)
        Appointment.objects.create(person=ok, slot=_mk_slot(room, d, time(10, 0), 5))
        resp = admin_client.get(reverse('average-age-list'),
                                {'studio': room.studio_id, 'start_time': '10:00'})
        assert resp.data['total'] == 1


@pytest.mark.django_db
class TestSumasEnBase:
    """ los totales de monto se suman en la base (Sum) y son float; 0 si no hay filas."""

    def _today(self):
        return timezone.localdate().isoformat()

    def test_gross_margin_suma_en_base(self, admin_client, person, studio):
        from apps.expenses.models import Expense
        from apps.expense_type.models import ExpenseType
        Payment.objects.create(person=person, amount='200.00', date=timezone.now(),
                               method='Efectivo', studio=studio)
        t = ExpenseType.objects.create(name='X')
        Expense.objects.create(amount='50.00', type=t, method='Efectivo', studio=studio)
        resp = admin_client.get(reverse('margen-bruto-list'),
                                {'start_date': self._today(), 'end_date': self._today()})
        assert resp.status_code == 200
        assert resp.data['total_income'] == 200.0
        assert resp.data['total_expenses'] == 50.0
        assert resp.data['gross_margin'] == 150.0
        assert isinstance(resp.data['total_income'], float)

    def test_gross_margin_sin_filas_devuelve_cero(self, admin_client):
        resp = admin_client.get(reverse('margen-bruto-list'),
                                {'start_date': self._today(), 'end_date': self._today()})
        assert resp.status_code == 200
        assert resp.data['total_income'] == 0
        assert resp.data['total_expenses'] == 0
        assert resp.data['gross_margin'] == 0

    def test_net_margin_sin_filas_devuelve_cero(self, admin_client):
        resp = admin_client.get(reverse('margen-neto-list'),
                                {'start_date': self._today(), 'end_date': self._today()})
        assert resp.status_code == 200
        assert resp.data['net_margin'] == 0
