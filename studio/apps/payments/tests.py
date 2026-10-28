import pytest
from datetime import date, time, timedelta
from decimal import Decimal
from dateutil.relativedelta import relativedelta
from django.urls import reverse
from .models import Payment, PaymentItem
from apps.people.models import Person, PersonActivePlan
from django.utils import timezone

_OMIT = object()  # sentinela: omitir una key del payload en _post


def _default_studio():
    """Estudio por defecto para tests que crean Payment sin foco en el estudio studio obligatorio)."""
    from apps.studios.models import Studio
    return Studio.objects.get_or_create(name='Test Studio')[0]


@pytest.mark.django_db
class TestPaymentSoftDelete:

    def test_delete_sets_deleted(self, person):
        payment = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=timezone.now(), method='Efectivo')
        payment.delete()
        payment.refresh_from_db()
        assert payment.deleted is not None

    def test_objects_hides_deleted(self, person):
        payment = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=timezone.now(), method='Efectivo')
        payment.delete()
        assert not Payment.objects.filter(pk=payment.pk).exists()

    def test_all_objects_includes_deleted(self, person):
        payment = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=timezone.now(), method='Efectivo')
        payment.delete()
        assert Payment.all_objects.filter(pk=payment.pk).exists()

    def test_all_objects_dead_returns_deleted(self, person):
        payment = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=timezone.now(), method='Efectivo')
        payment.delete()
        assert Payment.all_objects.dead().filter(pk=payment.pk).exists()

    def test_all_objects_alive_excludes_deleted(self, person):
        payment = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=timezone.now(), method='Efectivo')
        payment.delete()
        assert not Payment.all_objects.alive().filter(pk=payment.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user, person):
        payment = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=timezone.now(), method='Efectivo')
        payment.delete()
        qs = Payment.all_objects.for_user(admin_user)
        assert qs.filter(pk=payment.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user, person):
        payment = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=timezone.now(), method='Efectivo')
        payment.delete()
        qs = Payment.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=payment.pk).exists()

    def test_restore(self, person):
        payment = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=timezone.now(), method='Efectivo')
        payment.delete()
        payment.restore()
        payment.refresh_from_db()
        assert payment.deleted is None

    def test_hard_delete_removes_from_db(self, person):
        payment = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=timezone.now(), method='Efectivo')
        pk = payment.pk
        payment.hard_delete()
        assert not Payment.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestPaymentsViewForUser:
    URL = 'payment-amount-list'

    def test_admin_list_includes_deleted(self, admin_client, person):
        payment = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=timezone.now(), method='Efectivo')
        payment.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert payment.id in ids

    def test_consultor_list_excludes_deleted(self, consultor_client, person):
        payment = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=timezone.now(), method='Efectivo')
        payment.delete()
        response = consultor_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert payment.id not in ids

    def test_delete_endpoint_is_soft_delete(self, admin_client, person, monkeypatch):
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, "create", lambda **kwargs: None)
        payment = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=timezone.now(), method='Efectivo')
        url = reverse('payment-amount-detail', args=[payment.pk])
        response = admin_client.delete(url, data={'code': 'admin'}, format='json')
        assert response.status_code == 204
        assert Payment.all_objects.filter(pk=payment.pk).exists()
        payment.refresh_from_db()
        assert payment.deleted is not None


@pytest.mark.django_db
class TestPaymentRequiresItems:
    """ el pago single-plan legacy desaparece; se exige `items`."""
    URL = 'payment-amount-list'

    def test_create_without_items_returns_400(self, admin_client, person):
        resp = admin_client.post(reverse(self.URL), data={
            'person_id': person.id, 'amount': '1000', 'method': 'Efectivo',
            'code': 'admin', 'date': timezone.now().strftime('%Y-%m-%dT%H:%M:%S'),
        }, format='json')
        assert resp.status_code == 400, resp.data
        assert 'items' in str(resp.data).lower()

    def test_destroy_without_plan_returns_204(self, admin_client, person, monkeypatch):
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, 'create', lambda **kw: None)
        payment = Payment.objects.create(studio=_default_studio(), 
            person=person, amount='500', date=timezone.now(), method='Efectivo',
        )
        url = reverse('payment-amount-detail', args=[payment.pk])
        resp = admin_client.delete(url, data={'code': 'admin'}, format='json')
        assert resp.status_code == 204


@pytest.mark.django_db
class TestPaymentItemModel:
    # plans_type renombrado a plans_subtype en PaymentItem

    def test_final_amount_computed_on_save(self, payment_item):
        from decimal import Decimal
        # base=1000, discount=10% -> final=900
        assert payment_item.final_amount == Decimal('900.00')

    def test_final_amount_no_discount(self, payment, plans_subtype_a):
        from decimal import Decimal
        item = PaymentItem.objects.create(
            payment=payment,
            plans_subtype=plans_subtype_a,
            base_amount='500.00',
            discount_pct='0',
        )
        assert item.final_amount == Decimal('500.00')

    def test_soft_delete(self, payment_item):
        payment_item.delete()
        payment_item.refresh_from_db()
        assert payment_item.deleted is not None

    def test_objects_hides_deleted(self, payment_item):
        payment_item.delete()
        assert not PaymentItem.objects.filter(pk=payment_item.pk).exists()

    def test_restore(self, payment_item):
        payment_item.delete()
        payment_item.restore()
        payment_item.refresh_from_db()
        assert payment_item.deleted is None

    def test_hard_delete(self, payment_item):
        pk = payment_item.pk
        payment_item.hard_delete()
        assert not PaymentItem.all_objects.filter(pk=pk).exists()


# check_plans_availability
# Por qué: el servicio recibe plans_subtype_ids (no plans_type_ids) tras el
# refactor. Se verifica que la búsqueda de disponibilidad pase por
# PlansSubtype -> activity_subtype -> Slot.

@pytest.mark.django_db
class TestCheckPlansAvailability:

    def test_subtype_with_available_slot_is_ok(self, plans_subtype_a, slot_with_activity):
        from apps.payments.services import check_plans_availability
        result = check_plans_availability([plans_subtype_a.id])
        assert result == []

    def test_subtype_without_activity_subtype_is_skipped(self, plans_type):
        from apps.payments.services import check_plans_availability
        from apps.plans_subtype.models import PlansSubtype
        # PlansSubtype sin activity_subtype -> se omite en la validación
        ps = PlansSubtype.objects.create(name='Sin actividad', plan_type=plans_type)
        result = check_plans_availability([ps.id])
        assert result == []

    def test_subtype_with_no_slots_is_unavailable(self, plans_subtype_a):
        from apps.payments.services import check_plans_availability
        # plans_subtype_a tiene activity_subtype pero no hay ningún Slot creado
        result = check_plans_availability([plans_subtype_a.id])
        assert len(result) == 1
        assert result[0]['plans_subtype_id'] == plans_subtype_a.id
        assert 'plans_subtype_name' in result[0]

    def test_subtype_with_full_slot_is_unavailable(self, plans_subtype_a, activity_subtype, status, room):
        from apps.payments.services import check_plans_availability
        from apps.slots.models import Slot
        Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=1),
            start_time=time(9, 0), end_time=time(10, 0),
            availability=0,
            activity_subtype=activity_subtype,
        )
        result = check_plans_availability([plans_subtype_a.id])
        assert len(result) == 1

    def test_past_dated_slot_is_unavailable(self, plans_subtype_a, activity_subtype, status, room):
        from apps.payments.services import check_plans_availability
        from apps.slots.models import Slot
        Slot.objects.create(
            status=status, room=room,
            date=date.today() - timedelta(days=1),
            start_time=time(9, 0), end_time=time(10, 0),
            availability=5,
            activity_subtype=activity_subtype,
        )
        result = check_plans_availability([plans_subtype_a.id])
        assert len(result) == 1

    def test_future_dated_slot_is_available(self, plans_subtype_a, activity_subtype, status, room):
        from apps.payments.services import check_plans_availability
        from apps.slots.models import Slot
        Slot.objects.create(
            status=status, room=room,
            date=date.today() + timedelta(days=7),
            start_time=time(9, 0), end_time=time(10, 0),
            availability=5,
            activity_subtype=activity_subtype,
        )
        result = check_plans_availability([plans_subtype_a.id])
        assert result == []

    def test_deleted_slot_is_unavailable(self, plans_subtype_a, slot_with_activity):
        from apps.payments.services import check_plans_availability
        slot_with_activity.delete()
        result = check_plans_availability([plans_subtype_a.id])
        assert len(result) == 1

    def test_empty_ids_returns_empty(self, db):
        from apps.payments.services import check_plans_availability
        assert check_plans_availability([]) == []

    def test_nonexistent_subtype_reported_as_unavailable(self, db):
        from apps.payments.services import check_plans_availability
        result = check_plans_availability([99999])
        assert len(result) == 1
        assert result[0]['plans_subtype_id'] == 99999


# OverduePaymentsViewSet
# Por qué: identifica alumnos con planes vencidos que no renovaron.
# Se verifica que solo aparecen los vencidos, el filtro por person_id,
# y que los planes vigentes no se incluyen.

@pytest.mark.django_db
class TestOverduePayments:
    URL = 'overdue-payments-list'

    def test_returns_overdue_plans(self, admin_client, overdue_plan):
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert overdue_plan.id in ids

    def test_active_plan_not_included(self, admin_client, person_active_plan):
        # person_active_plan tiene exp_date futura -> no debe aparecer
        response = admin_client.get(reverse(self.URL))
        ids = [item['id'] for item in response.data]
        assert person_active_plan.id not in ids

    def test_filter_by_person_id(self, admin_client, overdue_plan, person, plans_subtype_a):
        from apps.people.models import Person
        other = Person.objects.create(name='Otro', last_name='Mora', dni='55555555')
        PersonActivePlan.objects.create(
            person=other,
            plans_subtype=plans_subtype_a,
            exp_date=date.today() - timedelta(days=5),
            sessions_total=4,
            sessions_remaining=2,
        )
        response = admin_client.get(reverse(self.URL), {'person_id': person.id})
        assert response.status_code == 200
        person_ids = {item['person'] for item in response.data}
        assert person_ids == {person.id}

    def test_soft_deleted_plan_not_included(self, admin_client, overdue_plan):
        overdue_plan.deleted = date.today()
        overdue_plan.save()
        response = admin_client.get(reverse(self.URL))
        ids = [item['id'] for item in response.data]
        assert overdue_plan.id not in ids

    def test_unauthenticated_returns_403(self):
        from rest_framework.test import APIClient
        response = APIClient().get(reverse(self.URL))
        assert response.status_code in (401, 403)

    def test_response_includes_person_and_subtype(self, admin_client, overdue_plan):
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        assert len(response.data) >= 1
        item = next(i for i in response.data if i['id'] == overdue_plan.id)
        assert 'person' in item
        assert 'plans_subtype' in item
        assert 'exp_date' in item


# Pago con uno o más planes
# Por qué: el create del PaymentViewSet debe poder recibir múltiples PaymentItem,
# cada uno asociado a un plans_subtype, calcular el total (con descuentos combo),
# crear los items y crear/renovar los planes activos del alumno (PersonActivePlan).
# Todo pago genera comprobante PDF, incluido el flujo multi-plan (ver
# generate_pdf_multi, que arma un comprobante detallado por cada plan).

@pytest.mark.django_db
class TestCreatePaymentWithItems:
    URL = 'payment-amount-list'

    def _patch_side_effects(self, monkeypatch):
        """Silencia Action y WhatsApp; stubea el PDF multi-plan (sin reportlab/red)."""
        from apps.actions.models import Action
        from apps.payments.views import PaymentViewSet

        monkeypatch.setattr(Action.objects, 'create', lambda **kw: None)
        monkeypatch.setattr(
            PaymentViewSet, 'generate_pdf_multi',
            lambda self, payment, person, active_plans, enriched: '/tmp/cp.pdf',
        )
        monkeypatch.setattr(PaymentViewSet, 'send_pdf', lambda s, path, per, msg: None)

    def _post(self, client, person, items, **extra):
        data = {
            'person_id': person.id,
            'code': 'admin',
            'method': 'Efectivo',
            'date': timezone.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'items': items,
        }
        from apps.studios.models import Studio
        studio, _ = Studio.objects.get_or_create(name='Test Studio')
        data['studio'] = studio.id
        data.update(extra)
        data = {k: v for k, v in data.items() if v is not _OMIT}
        return client.post(reverse(self.URL), data=data, format='json')

    def test_studio_is_required(self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch):
        # Payment.studio es obligatorio -> sin studio, 400 y no se crea el pago.
        self._patch_side_effects(monkeypatch)
        items = [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'}]
        r1 = self._post(admin_client, person, items, studio=_OMIT)
        assert r1.status_code == 400, r1.data
        assert 'studio' in r1.data
        assert not Payment.objects.filter(person=person).exists()
        r2 = self._post(admin_client, person, items, studio=None)
        assert r2.status_code == 400, r2.data
        r3 = self._post(admin_client, person, items)
        assert r3.status_code == 201, r3.data
        payment = Payment.objects.get(person=person)
        assert payment.studio_id is not None
        assert payment.amount == Decimal('1000.00')

    def test_non_numeric_amount_is_rejected(self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch):
        # amount es Decimal; un valor no numerico en el body -> 400.
        self._patch_side_effects(monkeypatch)
        items = [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'}]
        r = self._post(admin_client, person, items, amount='abc')
        assert r.status_code == 400, r.data

    def test_items_payment_generates_pdf_and_download_url(self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch):
        # Todo pago genera comprobante PDF: generate_pdf_multi se invoca, se
        # adjunta pdf_file y la respuesta trae pdf_download_url.
        from apps.actions.models import Action
        from apps.payments.views import PaymentViewSet

        called = {}

        def _gen(self, payment, person, active_plans, enriched):
            called['yes'] = True
            payment.pdf_file.name = 'payments/CP_test.pdf'
            payment.save(update_fields=['pdf_file'])
            return '/tmp/cp.pdf'

        monkeypatch.setattr(Action.objects, 'create', lambda **kw: None)
        monkeypatch.setattr(PaymentViewSet, 'generate_pdf_multi', _gen)
        monkeypatch.setattr(PaymentViewSet, 'send_pdf', lambda s, path, per, msg: None)

        resp = self._post(admin_client, person, [
            {'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'},
        ])
        assert resp.status_code == 201, resp.data
        assert called.get('yes') is True
        assert 'pdf_download_url' in resp.data
        payment = Payment.objects.get(person=person)
        assert payment.pdf_file
        assert 'warning' not in resp.data

    def test_items_without_available_slot_returns_400(self, admin_client, person, plans_subtype_a, monkeypatch):
        # plans_subtype_a tiene activity_subtype pero NO hay slot disponible ->
        # el flujo items debe validar disponibilidad (derivando el id desde items)
        # y rechazar con 400 sin crear el pago.
        self._patch_side_effects(monkeypatch)
        resp = self._post(admin_client, person, [
            {'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'},
        ])
        assert resp.status_code == 400, resp.data
        assert 'planes_sin_clases' in resp.data
        assert not Payment.objects.filter(person=person).exists()

    def test_items_with_available_slot_succeeds(self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch):
        # con un slot disponible para su activity_subtype, el pago se crea (201).
        self._patch_side_effects(monkeypatch)
        resp = self._post(admin_client, person, [
            {'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'},
        ])
        assert resp.status_code == 201, resp.data
        assert Payment.objects.filter(person=person).exists()

    def test_single_plan_creates_item_total_and_active_plan(self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch):
        self._patch_side_effects(monkeypatch)
        resp = self._post(admin_client, person, [
            {'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'},
        ])
        assert resp.status_code == 201, resp.data

        payment = Payment.objects.get(person=person)
        # items creados
        assert payment.items.count() == 1
        item = payment.items.first()
        assert item.plans_subtype_id == plans_subtype_a.id
        assert item.final_amount == Decimal('1000.00')
        # total
        assert Decimal(payment.amount) == Decimal('1000.00')
        # planes activos del alumno
        assert PersonActivePlan.objects.filter(person=person, plans_subtype=plans_subtype_a).count() == 1

    def test_multiple_plans_sum_total_and_create_all_items(self, admin_client, person, plans_subtype_a, plans_subtype_b, slot_with_activity, monkeypatch):
        self._patch_side_effects(monkeypatch)
        resp = self._post(admin_client, person, [
            {'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'},
            {'plans_subtype_id': plans_subtype_b.id, 'base_amount': '1500'},
        ])
        assert resp.status_code == 201, resp.data

        payment = Payment.objects.get(person=person)
        assert payment.items.count() == 2
        # sin combo cargado -> sin descuento -> total = suma simple
        assert Decimal(payment.amount) == Decimal('2500.00')
        # un plan activo por item
        assert PersonActivePlan.objects.filter(person=person).count() == 2

    def test_combo_discount_applied_to_items_and_total(self, admin_client, person, plans_subtype_a, plans_subtype_b, combo_plan_discount, slot_with_activity, monkeypatch):
        # combo_plan_discount: plans_subtype_a + plans_subtype_b -> 10%
        self._patch_side_effects(monkeypatch)
        resp = self._post(admin_client, person, [
            {'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'},
            {'plans_subtype_id': plans_subtype_b.id, 'base_amount': '1500'},
        ])
        assert resp.status_code == 201, resp.data

        payment = Payment.objects.get(person=person)
        items = {i.plans_subtype_id: i for i in payment.items.all()}
        assert items[plans_subtype_a.id].discount_pct == Decimal('10.00')
        assert items[plans_subtype_a.id].final_amount == Decimal('900.00')
        assert items[plans_subtype_b.id].final_amount == Decimal('1350.00')
        # total con descuento aplicado
        assert Decimal(payment.amount) == Decimal('2250.00')

    def test_active_plan_sessions_taken_from_subtype(self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch):
        self._patch_side_effects(monkeypatch)
        plans_subtype_a.sessions = 8
        plans_subtype_a.save()
        resp = self._post(admin_client, person, [
            {'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'},
        ])
        assert resp.status_code == 201, resp.data

        ap = PersonActivePlan.objects.get(person=person, plans_subtype=plans_subtype_a)
        assert ap.sessions_total == 8
        assert ap.sessions_remaining == 8

    def test_existing_active_plan_is_renewed_not_duplicated(self, admin_client, person, plans_subtype_a, person_active_plan, slot_with_activity, monkeypatch):
        # person_active_plan: mismo subtype, exp_date futura (+365d), sesiones 10/10
        self._patch_side_effects(monkeypatch)
        plans_subtype_a.sessions = 5
        plans_subtype_a.save()
        old_exp = person_active_plan.exp_date

        resp = self._post(admin_client, person, [
            {'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'},
        ])
        assert resp.status_code == 201, resp.data

        # no se duplica
        assert PersonActivePlan.objects.filter(person=person, plans_subtype=plans_subtype_a).count() == 1
        ap = PersonActivePlan.objects.get(person=person, plans_subtype=plans_subtype_a)
        # renovado: exp_date +1 mes desde la exp_date futura, sesiones recargadas
        assert ap.exp_date == old_exp + relativedelta(months=1)
        assert ap.sessions_remaining == 15
        assert ap.sessions_total == 15

    def test_invalid_base_amount_returns_400(self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch):
        # base_amount no numérico -> 400 (no 500), sin crear el pago.
        self._patch_side_effects(monkeypatch)
        resp = self._post(admin_client, person, [
            {'plans_subtype_id': plans_subtype_a.id, 'base_amount': 'abc'},
        ])
        assert resp.status_code == 400, resp.data
        assert not Payment.objects.filter(person=person).exists()

    def test_negative_base_amount_returns_400(self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch):
        self._patch_side_effects(monkeypatch)
        resp = self._post(admin_client, person, [
            {'plans_subtype_id': plans_subtype_a.id, 'base_amount': '-100'},
        ])
        assert resp.status_code == 400, resp.data
        assert not Payment.objects.filter(person=person).exists()

    def test_nonexistent_plans_subtype_returns_400(self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch):
        # plans_subtype_ids explícito (válido) evita que la validación de
        # disponibilidad intercepte; el id inexistente dentro de items debe
        # rechazarse con 400 por la validación de input (no 500 por DoesNotExist).
        self._patch_side_effects(monkeypatch)
        resp = self._post(
            admin_client, person,
            [{'plans_subtype_id': 999999, 'base_amount': '1000'}],
            plans_subtype_ids=[plans_subtype_a.id],
        )
        assert resp.status_code == 400, resp.data
        assert not Payment.objects.filter(person=person).exists()

    def test_non_numeric_plans_subtype_id_returns_400(self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch):
        # id no numérico en items (path derivado -> check_plans_availability): 400, no 500.
        self._patch_side_effects(monkeypatch)
        resp = self._post(admin_client, person, [
            {'plans_subtype_id': 'abc', 'base_amount': '1000'},
        ])
        assert resp.status_code == 400, resp.data
        assert not Payment.objects.filter(person=person).exists()

    def test_non_numeric_plans_subtype_id_explicit_ids_returns_400(self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch):
        # id no numérico en items con plans_subtype_ids explícito válido (path de
        # existencia en _create_with_items): 400, no 500.
        self._patch_side_effects(monkeypatch)
        resp = self._post(
            admin_client, person,
            [{'plans_subtype_id': 'abc', 'base_amount': '1000'}],
            plans_subtype_ids=[plans_subtype_a.id],
        )
        assert resp.status_code == 400, resp.data
        assert not Payment.objects.filter(person=person).exists()

    def test_empty_items_returns_400(self, admin_client, person, monkeypatch):
        # el flujo legacy (fallback sin items) desaparece; items=[] es
        # tan "sin items" como no mandarlo, y debe devolver 400.
        from apps.actions.models import Action
        monkeypatch.setattr(Action.objects, 'create', lambda **kw: None)
        resp = admin_client.post(reverse(self.URL), data={
            'person_id': person.id, 'amount': '2000', 'method': 'Efectivo',
            'code': 'admin', 'items': [],
            'date': timezone.now().strftime('%Y-%m-%dT%H:%M:%S'),
        }, format='json')
        assert resp.status_code == 400, resp.data
        assert not Payment.objects.filter(person=person).exists()


@pytest.mark.django_db
class TestUpdatePaymentMultiPlan:
    URL = 'payment-amount-list'
    DETAIL = 'payment-amount-detail'

    def _patch(self, monkeypatch):
        from apps.actions.models import Action
        from apps.payments.views import PaymentViewSet
        monkeypatch.setattr(Action.objects, 'create', lambda **kw: None)
        monkeypatch.setattr(PaymentViewSet, 'generate_pdf_multi',
                            lambda self, payment, person, active_plans, enriched: '/tmp/cp.pdf')
        monkeypatch.setattr(PaymentViewSet, 'send_pdf', lambda s, path, per, msg: None)

    def _crear_pago_items(self, admin_client, person, items):
        return admin_client.post(reverse(self.URL), data={
            'person_id': person.id, 'code': 'admin', 'method': 'Efectivo',
            'date': timezone.now().strftime('%Y-%m-%dT%H:%M:%S'), 'items': items,
            'studio': _default_studio().id,
        }, format='json')

    def test_editar_a_dos_planes_reconstruye_items_y_total(
        self, admin_client, person, plans_subtype_a, plans_subtype_b, slot_with_activity, monkeypatch
    ):
        self._patch(monkeypatch)
        # alta con 1 plan
        r = self._crear_pago_items(admin_client, person, [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'}])
        assert r.status_code == 201, r.data
        payment = Payment.objects.get(person=person)
        assert payment.items.count() == 1
        # editar a 2 planes
        resp = admin_client.put(reverse(self.DETAIL, args=[payment.pk]), data={
            'code': 'admin', 'method': 'Efectivo',
            'items': [
                {'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'},
                {'plans_subtype_id': plans_subtype_b.id, 'base_amount': '2000'},
            ],
        }, format='json')
        assert resp.status_code == 200, resp.data
        payment.refresh_from_db()
        assert payment.items.count() == 2          # reemplazó el set
        # total = suma de final_amount de los items
        total_items = sum(Decimal(str(i.final_amount)) for i in payment.items.all())
        assert Decimal(str(payment.amount)) == total_items

    def test_editar_no_toca_planes_activos(
        self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch
    ):
        self._patch(monkeypatch)
        r = self._crear_pago_items(admin_client, person, [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'}])
        payment = Payment.objects.get(person=person)
        antes = {(ap.plans_subtype_id, ap.sessions_remaining, ap.exp_date) for ap in PersonActivePlan.objects.filter(person=person)}
        admin_client.put(reverse(self.DETAIL, args=[payment.pk]), data={
            'code': 'admin', 'method': 'Efectivo',
            'items': [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1500'}],
        }, format='json')
        despues = {(ap.plans_subtype_id, ap.sessions_remaining, ap.exp_date) for ap in PersonActivePlan.objects.filter(person=person)}
        assert antes == despues   # la edición NO modifica PersonActivePlan

    def test_editar_con_item_invalido_400(
        self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch
    ):
        self._patch(monkeypatch)
        r = self._crear_pago_items(admin_client, person, [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'}])
        payment = Payment.objects.get(person=person)
        resp = admin_client.put(reverse(self.DETAIL, args=[payment.pk]), data={
            'code': 'admin', 'method': 'Efectivo',
            'items': [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': 'abc'}],
        }, format='json')
        assert resp.status_code == 400, resp.data
        payment.refresh_from_db()
        assert payment.items.count() == 1   # no se tocó nada

    def test_editar_mismo_plan_con_actividad_llena_no_bloquea_correccion(
        self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch
    ):
        """Corregir monto/método sin cambiar de plan no debe re-chequear la
        disponibilidad de un plan que la persona YA tenía en el pago original:
        aunque la actividad esté llena, la edición se guarda (200)."""
        self._patch(monkeypatch)
        r = self._crear_pago_items(admin_client, person, [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'}])
        assert r.status_code == 201, r.data
        payment = Payment.objects.get(person=person)
        # La actividad se llena DESPUÉS del alta.
        slot_with_activity.availability = 0
        slot_with_activity.save(update_fields=['availability'])
        resp = admin_client.put(reverse(self.DETAIL, args=[payment.pk]), data={
            'code': 'admin', 'method': 'Transferencia',
            'items': [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1500'}],
        }, format='json')
        assert resp.status_code == 200, resp.data
        payment.refresh_from_db()
        assert payment.method == 'Transferencia'
        assert payment.items.count() == 1

    def test_editar_plan_preexistente_como_string_no_bloquea_correccion(
        self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch
    ):
        """El `plans_subtype_id` puede llegar como string en el JSON; aun así, si
        corresponde a un plan que la persona ya tenía, no debe re-chequearse
        disponibilidad (comparación robusta a tipos str/int)."""
        self._patch(monkeypatch)
        r = self._crear_pago_items(admin_client, person, [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'}])
        payment = Payment.objects.get(person=person)
        slot_with_activity.availability = 0
        slot_with_activity.save(update_fields=['availability'])
        resp = admin_client.put(reverse(self.DETAIL, args=[payment.pk]), data={
            'code': 'admin', 'method': 'Transferencia',
            'items': [{'plans_subtype_id': str(plans_subtype_a.id), 'base_amount': '1500'}],
        }, format='json')
        assert resp.status_code == 200, resp.data

    def test_editar_agregando_plan_nuevo_con_actividad_llena_devuelve_400(
        self, admin_client, person, plans_subtype_a, plans_type, activity_subtype,
        slot_with_activity, monkeypatch
    ):
        """Agregar un plan NUEVO (no estaba en el pago original) cuya actividad
        está llena sí debe bloquear con 400: la guarda de disponibilidad se
        mantiene para el delta de planes nuevos."""
        from apps.plans_subtype.models import PlansSubtype
        self._patch(monkeypatch)
        r = self._crear_pago_items(admin_client, person, [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'}])
        payment = Payment.objects.get(person=person)
        # Plan nuevo sobre la misma actividad, que ahora está llena.
        ps_nuevo = PlansSubtype.objects.create(
            name='Nuevo', plan_type=plans_type, activity_subtype=activity_subtype,
        )
        slot_with_activity.availability = 0
        slot_with_activity.save(update_fields=['availability'])
        resp = admin_client.put(reverse(self.DETAIL, args=[payment.pk]), data={
            'code': 'admin', 'method': 'Efectivo',
            'items': [
                {'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'},
                {'plans_subtype_id': ps_nuevo.id, 'base_amount': '2000'},
            ],
        }, format='json')
        assert resp.status_code == 400, resp.data
        payment.refresh_from_db()
        assert payment.items.count() == 1   # no se tocó nada


@pytest.mark.django_db
class TestNormalizeAndValidateItems:
    def test_ok(self, plans_subtype_a):
        from apps.payments.services import normalize_and_validate_items
        norm, err = normalize_and_validate_items([{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'}])
        assert err is None
        assert norm == [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'}]

    def test_item_sin_campos(self):
        from apps.payments.services import normalize_and_validate_items
        norm, err = normalize_and_validate_items([{'plans_subtype_id': 1}])
        assert norm is None
        assert "plans_subtype_id" in err and "base_amount" in err

    def test_monto_invalido(self, plans_subtype_a):
        from apps.payments.services import normalize_and_validate_items
        norm, err = normalize_and_validate_items([{'plans_subtype_id': plans_subtype_a.id, 'base_amount': 'abc'}])
        assert norm is None
        assert "no es válido" in err

    def test_monto_negativo(self, plans_subtype_a):
        from apps.payments.services import normalize_and_validate_items
        norm, err = normalize_and_validate_items([{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '-5'}])
        assert norm is None

    def test_plan_inexistente(self):
        from apps.payments.services import normalize_and_validate_items
        norm, err = normalize_and_validate_items([{'plans_subtype_id': 999999, 'base_amount': '100'}])
        assert norm is None
        assert "no existen" in err


# Descuento por plan: PlanDiscount combinado con combos
# Por qué: cada plan puede tener un descuento propio (PlanDiscount, Task 1),
# independiente de los combos. La regla es tomar el MAYOR entre ambos, y
# registrar de dónde vino ('combo'|'plan'|'none') para trazabilidad.

@pytest.mark.django_db
class TestPlanDiscountInPricing:
    def _items(self, sid, amount='1000'):
        return [{'plans_subtype_id': sid, 'base_amount': amount}]

    def test_plan_discount_only(self, plans_subtype_a):
        from apps.plans_type.models import PlanDiscount
        from apps.payments.services import apply_combo_discounts
        PlanDiscount.objects.create(plans_subtype=plans_subtype_a, discount_pct='15.00')
        enriched, _ = apply_combo_discounts(self._items(plans_subtype_a.id))
        assert enriched[0]['discount_pct'] == Decimal('15.00')
        assert enriched[0]['discount_source'] == 'plan'

    def test_combo_beats_plan_when_higher(self, plans_subtype_a, plans_subtype_b, combo_plan_discount):
        # combo_plan_discount = 10% sobre A+B; plan discount de A = 5% -> gana combo
        from apps.plans_type.models import PlanDiscount
        from apps.payments.services import apply_combo_discounts
        PlanDiscount.objects.create(plans_subtype=plans_subtype_a, discount_pct='5.00')
        items = [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'},
                 {'plans_subtype_id': plans_subtype_b.id, 'base_amount': '1000'}]
        enriched, _ = apply_combo_discounts(items)
        a = next(e for e in enriched if e['plans_subtype_id'] == plans_subtype_a.id)
        assert a['discount_pct'] == Decimal('10.00')
        assert a['discount_source'] == 'combo'

    def test_plan_beats_combo_when_higher(self, plans_subtype_a, plans_subtype_b, combo_plan_discount):
        from apps.plans_type.models import PlanDiscount
        from apps.payments.services import apply_combo_discounts
        PlanDiscount.objects.create(plans_subtype=plans_subtype_a, discount_pct='25.00')
        items = [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'},
                 {'plans_subtype_id': plans_subtype_b.id, 'base_amount': '1000'}]
        enriched, _ = apply_combo_discounts(items)
        a = next(e for e in enriched if e['plans_subtype_id'] == plans_subtype_a.id)
        assert a['discount_pct'] == Decimal('25.00')
        assert a['discount_source'] == 'plan'

    def test_tie_plan_beats_combo(self, plans_subtype_a, plans_subtype_b, combo_plan_discount):
        """En empate (plan_pct == combo_pct > 0) el source debe ser 'plan'
        (más específico), para no atribuir mal el descuento en auditoría."""
        from apps.plans_type.models import PlanDiscount
        from apps.payments.services import apply_combo_discounts
        PlanDiscount.objects.create(plans_subtype=plans_subtype_a, discount_pct='10.00')  # == combo 10%
        items = [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'},
                 {'plans_subtype_id': plans_subtype_b.id, 'base_amount': '1000'}]
        enriched, _ = apply_combo_discounts(items)
        a = next(e for e in enriched if e['plans_subtype_id'] == plans_subtype_a.id)
        assert a['discount_pct'] == Decimal('10.00')
        assert a['discount_source'] == 'plan'

    def test_no_discount_source_none(self, plans_subtype_a):
        from apps.payments.services import apply_combo_discounts
        enriched, _ = apply_combo_discounts(self._items(plans_subtype_a.id))
        assert enriched[0]['discount_pct'] == Decimal('0')
        assert enriched[0]['discount_source'] == 'none'

    def test_deleted_plan_discount_ignored(self, plans_subtype_a):
        from apps.plans_type.models import PlanDiscount
        from apps.payments.services import apply_combo_discounts
        pd = PlanDiscount.objects.create(plans_subtype=plans_subtype_a, discount_pct='15.00')
        pd.delete()
        enriched, _ = apply_combo_discounts(self._items(plans_subtype_a.id))
        assert enriched[0]['discount_source'] == 'none'


@pytest.mark.django_db
class TestDiscountSourcePersisted:
    def _patch_side_effects(self, monkeypatch):
        """Silencia Action y WhatsApp; stubea el PDF multi-plan (mismo patrón que TestCreatePaymentWithItems)."""
        from apps.actions.models import Action
        from apps.payments.views import PaymentViewSet

        monkeypatch.setattr(Action.objects, 'create', lambda **kw: None)
        monkeypatch.setattr(
            PaymentViewSet, 'generate_pdf_multi',
            lambda self, payment, person, active_plans, enriched: '/tmp/cp.pdf',
        )
        monkeypatch.setattr(PaymentViewSet, 'send_pdf', lambda s, path, per, msg: None)

    def test_payment_item_records_plan_source(self, admin_client, person, plans_subtype_a, slot_with_activity, monkeypatch):
        from apps.plans_type.models import PlanDiscount
        self._patch_side_effects(monkeypatch)
        PlanDiscount.objects.create(plans_subtype=plans_subtype_a, discount_pct='15.00')

        resp = admin_client.post(reverse('payment-amount-list'), data={
            'person_id': person.id, 'code': 'admin', 'method': 'Efectivo',
            'date': timezone.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'studio': _default_studio().id,
            'items': [{'plans_subtype_id': plans_subtype_a.id, 'base_amount': '1000'}],
        }, format='json')
        assert resp.status_code == 201, resp.data

        item = PaymentItem.objects.get(payment__person=person, plans_subtype=plans_subtype_a)
        assert item.discount_source == 'plan'
        assert item.discount_pct == Decimal('15.00')


@pytest.mark.django_db
class TestPaymentsLastMonthKAN156:
    """/payments-last-month/ devuelve solo los pagos de los últimos 2 meses
    (rango fijo en backend, hoy − 2 meses -> hoy)."""
    URL = 'payments-last-month-list'

    def _pay(self, person, when, amount):
        return Payment.objects.create(studio=_default_studio(), person=person, amount=amount, date=when, method='Efectivo')

    def test_devuelve_solo_ultimos_2_meses(self, admin_client, person):
        now = timezone.now()
        reciente = self._pay(person, now, '100')
        medio = self._pay(person, now - relativedelta(months=1), '200')
        viejo = self._pay(person, now - relativedelta(months=3), '300')  # fuera de la ventana

        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        ids = {p['id'] for p in resp.data}
        assert reciente.id in ids
        assert medio.id in ids
        assert viejo.id not in ids

    def test_borde_2_meses_inclusivo(self, admin_client, person):
        # Determinista: se usa la misma referencia que el endpoint (localdate) y
        # datetimes aware al mediodía, para no depender de la hora/tz del server.
        from datetime import datetime
        start_date = timezone.localdate() - relativedelta(months=2)
        aware_noon = lambda d: timezone.make_aware(datetime.combine(d, time(12, 0)))
        borde_in = self._pay(person, aware_noon(start_date), '100')              # inicio de la ventana
        borde_out = self._pay(person, aware_noon(start_date - timedelta(days=1)), '200')  # 1 día antes

        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        ids = {p['id'] for p in resp.data}
        assert borde_in.id in ids
        assert borde_out.id not in ids

    def test_soft_deleted_no_aparece(self, admin_client, person):
        now = timezone.now()
        vivo = self._pay(person, now, '100')
        borrado = self._pay(person, now, '200')
        borrado.delete()  # soft-delete

        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        ids = {p['id'] for p in resp.data}
        assert vivo.id in ids
        assert borrado.id not in ids

    def test_sin_pagos_en_ventana_devuelve_404(self, admin_client, person):
        # Comportamiento actual del endpoint: 404 si no hay pagos en la ventana.
        self._pay(person, timezone.now() - relativedelta(months=5), '100')  # fuera
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 404


@pytest.mark.django_db
class TestReceiptContentKAN262:
    """Contenido del comprobante PDF: encabezado DENISE SOULES STUDIO, planes sin
    vencimiento individual, próximo vencimiento general + aviso de baja a los 7
    días con la fecha dinámica en dd-mm-aaaa."""

    class _P:
        name = 'Lola'
        last_name = 'Wulff'

    def _content(self, next_exp):
        from apps.payments.views import build_receipt_content
        enriched = [
            {'plans_subtype_id': 1, 'final_amount': Decimal('4750.00')},
            {'plans_subtype_id': 2, 'final_amount': Decimal('9500.00')},
        ]
        names = {1: 'Mañana', 2: 'Tarde'}
        return build_receipt_content(self._P(), '28-08-2026', enriched, names, next_exp)

    def test_encabezado_denise_sin_aura(self):
        content = self._content(date(2026, 10, 28))
        texts = [t for _, t in content]
        assert ('subtitle', 'DENISE SOULES STUDIO') in content
        assert all('Aura Estudio Pilates' not in t for t in texts)

    def test_planes_sin_vencimiento_individual(self):
        content = self._content(date(2026, 10, 28))
        plan_lines = [t for k, t in content if k == 'normal' and '&bull;' in t]
        assert len(plan_lines) == 2
        assert all('vence' not in t for t in plan_lines)
        assert any('Mañana' in t and '$4750.00' in t for t in plan_lines)

    def test_total(self):
        texts = [t for _, t in self._content(date(2026, 10, 28))]
        assert any('Total: $14250.00' in t for t in texts)

    def test_proximo_vencimiento_y_aviso_con_fecha(self):
        texts = [t for _, t in self._content(date(2026, 10, 28))]
        assert any('próximo vencimiento es el' in t and '28-10-2026' in t for t in texts)
        aviso = [t for t in texts if 'dada de baja automáticamente' in t]
        assert len(aviso) == 1
        assert '7 días' in aviso[0]
        assert '(28-10-2026)' in aviso[0]  # fecha dinámica dd-mm-aaaa entre paréntesis

    def test_sin_next_exp_omite_vencimiento_y_aviso(self):
        texts = [t for _, t in self._content(None)]
        assert not any('próximo vencimiento' in t for t in texts)
        assert not any('dada de baja' in t for t in texts)
        # el resto (encabezado, planes, total) sí se genera
        assert any('Total:' in t for t in texts)


# filtro opcional por estudio en /payments/

MSG_400 = "El parámetro 'studio' debe ser un número entero positivo."


@pytest.mark.django_db
class TestPaymentsStudioFilterKAN144:
    URL = 'payment-amount-list'  # basename registrado para /payments/

    @pytest.fixture
    def data(self, person, studio, studio_b):
        mk = lambda st, amt: Payment.objects.create(
            person=person, amount=amt, date=timezone.now(), method='Efectivo', studio=st)
        a1, a2, b1 = mk(studio, '100'), mk(studio, '200'), mk(studio_b, '300')
        return {'a': {a1.id, a2.id}, 'b': {b1.id}}

    def _ids(self, response):
        return {p['id'] for p in response.data}

    def test_url_es_payments(self):
        assert reverse(self.URL) == '/payments/'

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

    def test_estudio_dado_de_baja_envuelve_respuesta(self, admin_client, person, deleted_studio):
        p = Payment.objects.create(person=person, amount='10', date=timezone.now(),
                                   method='Efectivo', studio=deleted_studio)
        r = admin_client.get(reverse(self.URL), {'studio': deleted_studio.id})
        assert r.status_code == 200
        assert r.data['detail'] == f'El estudio con id {deleted_studio.id} está dado de baja.'
        assert [x['id'] for x in r.data['results']] == [p.id]


# filtro opcional por estudio en /cash_journal_today/

@pytest.mark.django_db
class TestCashJournalTodayStudioFilterKAN147:
    URL = 'cash_journal_today-list'

    @pytest.fixture(autouse=True)
    def _hoy_local(self, monkeypatch):
        # La vista usa datetime.now().date() (hora del server) contra date__date
        # (zona de settings). No se cambia esa lógica; en el test se alinea el
        # "ahora" con la hora local para que no dependa de la hora en que corre.
        import datetime as _dt
        import apps.payments.views as views

        class _FakeDatetime(_dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return timezone.localtime().replace(tzinfo=None)

        monkeypatch.setattr(views, 'datetime', _FakeDatetime)

    @pytest.fixture
    def data(self, person, studio, studio_b):
        from apps.expenses.models import Expense
        from apps.expense_type.models import ExpenseType
        t = ExpenseType.objects.create(name='Luz')
        pay = lambda st, amt, m: Payment.objects.create(
            person=person, amount=amt, date=timezone.now(), method=m, studio=st)
        exp = lambda st, amt, m: Expense.objects.create(amount=amt, type=t, method=m, studio=st)
        pa = [pay(studio, '1000', 'Efectivo'), pay(studio, '500', 'Transferencia')]
        pb = [pay(studio_b, '2000', 'efectivo')]
        ea = [exp(studio, '100', 'Efectivo')]
        eb = [exp(studio_b, '300', 'Transferencia'), exp(studio_b, '50', 'Efectivo')]
        # Movimientos de otro día y eliminados: no cuentan en ningún caso
        Payment.objects.create(person=person, amount='9999', method='Efectivo', studio=studio,
                               date=timezone.now() - timedelta(days=2))
        borrado = pay(studio, '7777', 'Efectivo'); borrado.delete()
        return {'pa': pa, 'pb': pb, 'ea': ea, 'eb': eb}

    def _ids(self, items):
        return {x['id'] for x in items}

    def test_global_sin_filtro(self, admin_client, data):
        r = admin_client.get(reverse(self.URL))
        assert r.status_code == 200
        assert r.data['studio'] is None
        assert self._ids(r.data['payments']) == {p.id for p in data['pa'] + data['pb']}
        assert self._ids(r.data['expenses']) == {e.id for e in data['ea'] + data['eb']}
        assert r.data['total_ingresos'] == 3500.0
        assert r.data['total_gastos'] == 450.0
        assert r.data['caja_total'] == 3050.0
        assert r.data['total_ingresos_efectivo'] == 3000.0
        assert r.data['total_ingresos_transferencia'] == 500.0
        assert r.data['total_gastos_efectivo'] == 150.0
        assert r.data['total_gastos_transferencia'] == 300.0
        assert r.data['diferencia_efectivo'] == 2850.0
        assert r.data['diferencia_transferencia'] == 200.0

    def test_estudio_a(self, admin_client, data, studio):
        r = admin_client.get(reverse(self.URL), {'studio': studio.id})
        assert r.status_code == 200
        assert r.data['studio'] == [studio.id]
        assert self._ids(r.data['payments']) == {p.id for p in data['pa']}
        assert self._ids(r.data['expenses']) == {e.id for e in data['ea']}
        assert r.data['total_ingresos'] == 1500.0
        assert r.data['total_gastos'] == 100.0
        assert r.data['caja_total'] == 1400.0
        assert r.data['total_ingresos_efectivo'] == 1000.0
        assert r.data['total_ingresos_transferencia'] == 500.0

    def test_estudio_b(self, admin_client, data, studio_b):
        r = admin_client.get(reverse(self.URL), {'studio': studio_b.id})
        assert r.status_code == 200
        assert r.data['studio'] == [studio_b.id]
        assert self._ids(r.data['payments']) == {p.id for p in data['pb']}
        assert r.data['total_ingresos'] == 2000.0
        assert r.data['total_gastos'] == 350.0
        assert r.data['caja_total'] == 1650.0
        assert r.data['total_gastos_transferencia'] == 300.0

    def test_global_es_suma_de_estudios(self, admin_client, data, studio, studio_b):
        g = admin_client.get(reverse(self.URL)).data
        a = admin_client.get(reverse(self.URL), {'studio': studio.id}).data
        b = admin_client.get(reverse(self.URL), {'studio': studio_b.id}).data
        ab = admin_client.get(reverse(self.URL) + f'?studio={studio.id},{studio_b.id}').data
        for key in ('caja_total', 'total_ingresos', 'total_gastos', 'total_ingresos_efectivo',
                    'total_gastos_efectivo', 'total_ingresos_transferencia',
                    'total_gastos_transferencia', 'diferencia_efectivo', 'diferencia_transferencia'):
            assert g[key] == a[key] + b[key] == ab[key], key
        assert ab['studio'] == [studio.id, studio_b.id]

    @pytest.mark.parametrize('value', ['abc', '-1', ''])
    def test_studio_invalido_400(self, admin_client, data, value):
        r = admin_client.get(reverse(self.URL) + f'?studio={value}')
        assert r.status_code == 400
        assert r.data == {'detail': "El parámetro 'studio' debe ser un número entero positivo."}

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
        assert r.data['total_ingresos'] == 1500.0

    def test_estudio_sin_datos_200_totales_cero(self, admin_client, data, empty_studio):
        r = admin_client.get(reverse(self.URL), {'studio': empty_studio.id})
        assert r.status_code == 200
        assert r.data['payments'] == [] and r.data['expenses'] == []
        assert r.data['caja_total'] == 0 and r.data['total_ingresos'] == 0 and r.data['total_gastos'] == 0
        assert 'detail' not in r.data

    def test_global_sin_movimientos_sigue_404(self, admin_client, db):
        r = admin_client.get(reverse(self.URL))
        assert r.status_code == 404
        assert r.data == {'detail': 'No se encontraron pagos ni gastos para hoy.'}

    def test_estudio_dado_de_baja_avisa(self, admin_client, person, deleted_studio):
        p = Payment.objects.create(person=person, amount='80', date=timezone.now(),
                                   method='Efectivo', studio=deleted_studio)
        r = admin_client.get(reverse(self.URL), {'studio': deleted_studio.id})
        assert r.status_code == 200
        assert r.data['detail'] == f'El estudio con id {deleted_studio.id} está dado de baja.'
        assert self._ids(r.data['payments']) == {p.id}
        assert r.data['total_ingresos'] == 80.0

    def test_monto_no_numerico_no_rompe(self, admin_client, person, studio):
        Payment.objects.create(person=person, amount=None, date=timezone.now(),
                               method='Efectivo', studio=studio)
        Payment.objects.create(person=person, amount='10', date=timezone.now(),
                               method=None, studio=studio)
        r = admin_client.get(reverse(self.URL), {'studio': studio.id})
        assert r.status_code == 200
        assert r.data['total_ingresos'] == 10.0
        assert r.data['total_ingresos_efectivo'] == 0


# filtro opcional por estudio en /cash_journal/ (caja por rango)

@pytest.mark.django_db
class TestCashJournalRangeStudioFilterKAN147:
    URL = 'cash_journal-list'

    @pytest.fixture
    def rango(self):
        hoy = timezone.localdate()
        return {'start_date': (hoy - timedelta(days=1)).isoformat(),
                'end_date': (hoy + timedelta(days=1)).isoformat()}

    @pytest.fixture
    def data(self, person, studio, studio_b):
        from apps.expenses.models import Expense
        from apps.expense_type.models import ExpenseType
        t = ExpenseType.objects.create(name='Luz')
        pay = lambda st, amt, m: Payment.objects.create(
            person=person, amount=amt, date=timezone.now(), method=m, studio=st)
        exp = lambda st, amt, m: Expense.objects.create(amount=amt, type=t, method=m, studio=st)
        pa = [pay(studio, '1000', 'Efectivo'), pay(studio, '500', 'Transferencia')]
        pb = [pay(studio_b, '2000', 'Efectivo')]
        ea = [exp(studio, '100', 'Efectivo')]
        eb = [exp(studio_b, '300', 'Transferencia')]
        return {'pa': pa, 'pb': pb, 'ea': ea, 'eb': eb}

    def test_global_sin_filtro(self, admin_client, data, rango):
        r = admin_client.get(reverse(self.URL), rango)
        assert r.status_code == 200
        assert r.data['studio'] is None
        assert r.data['caja_total'] == 3100.0
        assert len(r.data['payments']) == 3 and len(r.data['expenses']) == 2

    def test_estudio_a(self, admin_client, data, rango, studio):
        r = admin_client.get(reverse(self.URL), {**rango, 'studio': studio.id})
        assert r.status_code == 200
        assert r.data['studio'] == [studio.id]
        assert {p['id'] for p in r.data['payments']} == {p.id for p in data['pa']}
        assert r.data['caja_total'] == 1400.0
        assert r.data['total_ingresos_efectivo'] == 1000.0
        assert r.data['total_ingresos_transferencia'] == 500.0

    def test_estudio_b(self, admin_client, data, rango, studio_b):
        r = admin_client.get(reverse(self.URL), {**rango, 'studio': studio_b.id})
        assert r.status_code == 200
        assert r.data['caja_total'] == 1700.0
        assert r.data['total_gastos_transferencia'] == 300.0

    def test_global_es_suma_de_estudios(self, admin_client, data, rango, studio, studio_b):
        g = admin_client.get(reverse(self.URL), rango).data
        a = admin_client.get(reverse(self.URL), {**rango, 'studio': studio.id}).data
        b = admin_client.get(reverse(self.URL), {**rango, 'studio': studio_b.id}).data
        ab = admin_client.get(reverse(self.URL) + f'?start_date={rango["start_date"]}'
                              f'&end_date={rango["end_date"]}&studio={studio.id},{studio_b.id}').data
        for key in ('caja_total', 'total_ingresos_efectivo', 'total_gastos_efectivo',
                    'total_ingresos_transferencia', 'total_gastos_transferencia'):
            assert g[key] == a[key] + b[key] == ab[key], key

    @pytest.mark.parametrize('value', ['abc', '-1', ''])
    def test_studio_invalido_400(self, admin_client, data, rango, value):
        r = admin_client.get(reverse(self.URL) + f'?start_date={rango["start_date"]}'
                             f'&end_date={rango["end_date"]}&studio={value}')
        assert r.status_code == 400
        assert r.data == {'detail': "El parámetro 'studio' debe ser un número entero positivo."}

    def test_studio_inexistente_404(self, admin_client, data, rango):
        r = admin_client.get(reverse(self.URL), {**rango, 'studio': 999999})
        assert r.status_code == 404
        assert r.data == {'detail': 'No existe un estudio con id 999999.'}

    def test_usuario_sin_permiso_403(self, consultor_client, data, rango, studio):
        # /cash_journal/ es solo Admin/Super: el Consultor sigue sin acceso.
        r = consultor_client.get(reverse(self.URL), {**rango, 'studio': studio.id})
        assert r.status_code == 403

    def test_usuario_con_permiso_200(self, super_client, data, rango, studio):
        r = super_client.get(reverse(self.URL), {**rango, 'studio': studio.id})
        assert r.status_code == 200

    def test_estudio_sin_datos_200_totales_cero(self, admin_client, data, rango, empty_studio):
        r = admin_client.get(reverse(self.URL), {**rango, 'studio': empty_studio.id})
        assert r.status_code == 200
        assert r.data['payments'] == [] and r.data['expenses'] == []
        assert r.data['caja_total'] == 0 and r.data['detalles_por_dia'] == []

    def test_global_sin_movimientos_sigue_404(self, admin_client, rango):
        r = admin_client.get(reverse(self.URL), rango)
        assert r.status_code == 404

    def test_estudio_dado_de_baja_avisa(self, admin_client, person, rango, deleted_studio):
        Payment.objects.create(person=person, amount='80', date=timezone.now(),
                               method='Efectivo', studio=deleted_studio)
        r = admin_client.get(reverse(self.URL), {**rango, 'studio': deleted_studio.id})
        assert r.status_code == 200
        assert r.data['detail'] == f'El estudio con id {deleted_studio.id} está dado de baja.'
        assert r.data['caja_total'] == 80.0


# "hoy" de la caja diaria debe usar la fecha local (America/Argentina/Buenos_Aires),
# no el reloj naive del servidor. 01:00 UTC del 15 == 22:00 BA del 14.
@pytest.mark.django_db
class TestCajaDiariaFechaLocal:

    @pytest.fixture
    def frozen_ba_night(self, monkeypatch):
        import datetime as dt
        fixed = dt.datetime(2026, 6, 15, 1, 0, tzinfo=dt.timezone.utc)
        monkeypatch.setattr(timezone, 'now', lambda: fixed)
        return fixed

    def test_payments_today_usa_fecha_local(self, admin_client, person, frozen_ba_night):
        p = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=frozen_ba_night, method='Efectivo')
        response = admin_client.get(reverse('payments-today-list'))
        assert response.status_code == 200
        assert [item['id'] for item in response.data] == [p.id]

    def test_cash_journal_today_usa_fecha_local(self, admin_client, person, frozen_ba_night):
        p = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=frozen_ba_night, method='Efectivo')
        response = admin_client.get(reverse('cash_journal_today-list'))
        assert response.status_code == 200
        assert [item['id'] for item in response.data['payments']] == [p.id]

    def test_teacher_cash_journal_today_usa_fecha_local(self, admin_client, person, frozen_ba_night):
        p = Payment.objects.create(studio=_default_studio(), person=person, amount='1000', date=frozen_ba_night, method='Efectivo')
        response = admin_client.get(reverse('teacher_cash_journal_today-list'))
        assert response.status_code == 200
        assert [item['id'] for item in response.data['payments']] == [p.id]


# helper puro de parseo de monto para migraciones

@pytest.mark.parametrize("raw,expected", [
    ("1234", "1234.00"),
    ("1234.5", "1234.50"),
    ("1234,50", "1234.50"),       # coma decimal
    ("1.234,50", "1234.50"),      # miles . + coma decimal
    ("1,234.50", "1234.50"),      # miles , + punto decimal
    ("  10  ", "10.00"),
    ("", "0.00"),
    (None, "0.00"),
    ("abc", "0.00"),
    ("$100", "100.00"),
])
def test_parse_amount_to_decimal_str(raw, expected):
    from apps.payments.money_migration_utils import parse_amount_to_decimal_str
    assert parse_amount_to_decimal_str(raw) == expected
