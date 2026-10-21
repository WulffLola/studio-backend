import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework.test import APIClient
from .models import PlansType, ComboPlanDiscount
from apps.plans_subtype.models import PlansSubtype
from apps.payment_method.models import PaymentMethod


# Fixtures locales

@pytest.fixture
def subtype_a(plans_type):
    return PlansSubtype.objects.create(name='1 día', plans_type=plans_type)


@pytest.fixture
def subtype_b(plans_type_b):
    return PlansSubtype.objects.create(name='2 días', plans_type=plans_type_b)


@pytest.fixture
def subtype_c(plans_type):
    return PlansSubtype.objects.create(name='3 días', plans_type=plans_type)


@pytest.mark.django_db
class TestPlansTypeSoftDelete:

    def test_delete_sets_deleted(self, db):
        pt = PlansType.objects.create(name='Test')
        pt.delete()
        pt.refresh_from_db()
        assert pt.deleted is not None

    def test_objects_hides_deleted(self, db):
        pt = PlansType.objects.create(name='Test')
        pt.delete()
        assert not PlansType.objects.filter(pk=pt.pk).exists()

    def test_restore(self, db):
        pt = PlansType.objects.create(name='Test')
        pt.delete()
        pt.restore()
        pt.refresh_from_db()
        assert pt.deleted is None


@pytest.mark.django_db
class TestComboPlanDiscountSoftDelete:

    def test_delete_sets_deleted(self, combo_plan_discount):
        combo_plan_discount.delete()
        combo_plan_discount.refresh_from_db()
        assert combo_plan_discount.deleted is not None

    def test_objects_hides_deleted(self, combo_plan_discount):
        combo_plan_discount.delete()
        assert not ComboPlanDiscount.objects.filter(pk=combo_plan_discount.pk).exists()

    def test_all_objects_includes_deleted(self, combo_plan_discount):
        combo_plan_discount.delete()
        assert ComboPlanDiscount.all_objects.filter(pk=combo_plan_discount.pk).exists()

    def test_all_objects_dead_returns_deleted(self, combo_plan_discount):
        combo_plan_discount.delete()
        assert ComboPlanDiscount.all_objects.dead().filter(pk=combo_plan_discount.pk).exists()

    def test_all_objects_alive_excludes_deleted(self, combo_plan_discount):
        combo_plan_discount.delete()
        assert not ComboPlanDiscount.all_objects.alive().filter(pk=combo_plan_discount.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user, combo_plan_discount):
        combo_plan_discount.delete()
        qs = ComboPlanDiscount.all_objects.for_user(admin_user)
        assert qs.filter(pk=combo_plan_discount.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user, combo_plan_discount):
        combo_plan_discount.delete()
        qs = ComboPlanDiscount.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=combo_plan_discount.pk).exists()

    def test_restore(self, combo_plan_discount):
        combo_plan_discount.delete()
        combo_plan_discount.restore()
        combo_plan_discount.refresh_from_db()
        assert combo_plan_discount.deleted is None

    def test_hard_delete_removes_from_db(self, combo_plan_discount):
        pk = combo_plan_discount.pk
        combo_plan_discount.hard_delete()
        assert not ComboPlanDiscount.all_objects.filter(pk=pk).exists()

    def test_two_plans_in_combo(self, combo_plan_discount, plans_subtype_a, plans_subtype_b):
        """El combo puede tener 2 planes (caso base)."""
        assert combo_plan_discount.plans.count() == 2

    def test_n_plans_in_combo(self, subtype_a, subtype_b, subtype_c):
        """El combo puede tener N planes, no solo 2."""
        combo = ComboPlanDiscount.objects.create(discount_pct='15.00')
        combo.plans.set([subtype_a, subtype_b, subtype_c])
        assert combo.plans.count() == 3


@pytest.mark.django_db
class TestComboPlanDiscountView:
    URL = 'combo-plan-discount-list'

    def test_admin_can_list(self, admin_client, combo_plan_discount):
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert combo_plan_discount.id in ids

    def test_admin_list_includes_deleted(self, admin_client, combo_plan_discount):
        combo_plan_discount.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert combo_plan_discount.id in ids

    def test_admin_can_create_with_two_subtypes(self, admin_client, subtype_a, subtype_b):
        """
        Creación con dos subtypes. Ahora el campo es plans_ids (lista de IDs),
        ya no plan_type_a_id / plan_type_b_id.
        """
        response = admin_client.post(reverse(self.URL), data={
            'plans_ids': [subtype_a.id, subtype_b.id],
            'discount_pct': '15.00',
        }, format='json')
        assert response.status_code == 201
        combo = ComboPlanDiscount.objects.latest('id')
        assert combo.plans.count() == 2

    def test_admin_can_create_with_three_subtypes(self, admin_client, subtype_a, subtype_b, subtype_c):
        """El endpoint acepta N planes, no solo 2."""
        response = admin_client.post(reverse(self.URL), data={
            'plans_ids': [subtype_a.id, subtype_b.id, subtype_c.id],
            'discount_pct': '20.00',
        }, format='json')
        assert response.status_code == 201
        combo = ComboPlanDiscount.objects.latest('id')
        assert combo.plans.count() == 3

    def test_response_includes_subtype_fields(self, admin_client, subtype_a, subtype_b):
        """La respuesta expone id, name y plans_type_name de cada subtype."""
        admin_client.post(reverse(self.URL), data={
            'plans_ids': [subtype_a.id, subtype_b.id],
            'discount_pct': '10.00',
        }, format='json')
        response = admin_client.get(reverse(self.URL))
        combo = response.data[0]
        plan = combo['plans'][0]
        assert 'id' in plan
        assert 'name' in plan
        assert 'plans_type_name' in plan
        assert 'price' not in plan

    def test_delete_endpoint_is_soft_delete(self, admin_client, combo_plan_discount):
        url = reverse('combo-plan-discount-detail', args=[combo_plan_discount.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert ComboPlanDiscount.all_objects.filter(pk=combo_plan_discount.pk).exists()
        combo_plan_discount.refresh_from_db()
        assert combo_plan_discount.deleted is not None


@pytest.mark.django_db
class TestAvailablePlansView:
    URL = 'available-plans-list'

    def test_anonymous_can_access(self, db):
        client = APIClient()
        response = client.get(reverse(self.URL))
        assert response.status_code == 200
        assert 'plans' in response.data
        assert 'combos' in response.data

    def test_returns_active_plan_subtypes_only(self, db, plans_subtype_a, plans_subtype_b):
        """
        'plans' ahora es una lista de PlansSubtype (no PlansType).
        Solo aparecen los subtypes activos (deleted__isnull=True).
        """
        plans_subtype_b.delete()
        client = APIClient()
        response = client.get(reverse(self.URL))
        ids = [p['id'] for p in response.data['plans']]
        assert plans_subtype_a.id in ids
        assert plans_subtype_b.id not in ids

    def test_plan_includes_type_name(self, db, plans_subtype_a):
        """Cada plan expone name y plans_type_name (nombre del tipo padre). Sin precio."""
        client = APIClient()
        response = client.get(reverse(self.URL))
        plan = next(p for p in response.data['plans'] if p['id'] == plans_subtype_a.id)
        assert plan['plans_type_name'] == plans_subtype_a.plans_type.name
        assert 'price' not in plan

    def test_plan_includes_activity_subtypes(self, db, plans_subtype_a, activity_subtype):
        """
        Cada plan incluye las subactividades de su tipo padre.
        activity_subtype del conftest tiene plans_type=plans_type, que es el padre
        de plans_subtype_a.
        """
        client = APIClient()
        response = client.get(reverse(self.URL))
        plan = next(p for p in response.data['plans'] if p['id'] == plans_subtype_a.id)
        assert 'activity_subtypes' in plan
        ids = [a['id'] for a in plan['activity_subtypes']]
        assert activity_subtype.id in ids

    def test_deleted_subtype_excluded_from_plans(self, db, plans_subtype_a):
        """Un PlansSubtype eliminado no aparece en la lista de planes."""
        plans_subtype_a.delete()
        client = APIClient()
        response = client.get(reverse(self.URL))
        ids = [p['id'] for p in response.data['plans']]
        assert plans_subtype_a.id not in ids

    def test_returns_active_combos(self, combo_plan_discount):
        client = APIClient()
        response = client.get(reverse(self.URL))
        combo_ids = [c['id'] for c in response.data['combos']]
        assert combo_plan_discount.id in combo_ids

    def test_deleted_combo_excluded(self, combo_plan_discount):
        combo_plan_discount.delete()
        client = APIClient()
        response = client.get(reverse(self.URL))
        combo_ids = [c['id'] for c in response.data['combos']]
        assert combo_plan_discount.id not in combo_ids

    def test_combo_has_discount_pct(self, combo_plan_discount):
        client = APIClient()
        response = client.get(reverse(self.URL))
        combo = next(c for c in response.data['combos'] if c['id'] == combo_plan_discount.id)
        assert 'discount_pct' in combo
        assert combo['discount_pct'] == '10.00'

    def test_combo_exposes_subtypes_not_types(self, combo_plan_discount):
        """
        El combo debe retornar 'plans' (subtypes) y NO 'plan_type_a'/'plan_type_b'.
        El frontend necesita el subtype concreto (con precio), no la categoría.
        """
        client = APIClient()
        response = client.get(reverse(self.URL))
        combo = next(c for c in response.data['combos'] if c['id'] == combo_plan_discount.id)
        assert 'plans' in combo
        assert 'plan_type_a' not in combo
        assert 'plan_type_b' not in combo
        assert len(combo['plans']) == 2
        # Cada plan expone id, name y plans_type_name (sin price)
        for plan in combo['plans']:
            assert 'id' in plan
            assert 'name' in plan
            assert 'plans_type_name' in plan
            assert 'price' not in plan

    def test_combo_supports_three_plans(self, plans_type, plans_type_b):
        """Verifica que el endpoint devuelve correctamente un combo con 3 planes."""
        from apps.plans_subtype.models import PlansSubtype
        s1 = PlansSubtype.objects.create(name='A', plans_type=plans_type)
        s2 = PlansSubtype.objects.create(name='B', plans_type=plans_type_b)
        s3 = PlansSubtype.objects.create(name='C', plans_type=plans_type)
        combo = ComboPlanDiscount.objects.create(discount_pct='25.00')
        combo.plans.set([s1, s2, s3])

        client = APIClient()
        response = client.get(reverse(self.URL))
        found = next(c for c in response.data['combos'] if c['id'] == combo.id)
        assert len(found['plans']) == 3


# PricesViewSet

@pytest.mark.django_db
class TestPricesViewSet:
    URL = 'prices-list'

    def test_anonymous_can_access(self, db):
        """Endpoint público — no requiere autenticación."""
        client = APIClient()
        response = client.get(reverse(self.URL))
        assert response.status_code == 200

    def test_returns_plan_subtypes_as_root(self, plans_subtype_a):
        """
        El root de la lista es PlansSubtype, no PlansType.
        Antes retornaba PlansType con subtypes anidados.
        """
        client = APIClient()
        response = client.get(reverse(self.URL))
        ids = [p['id'] for p in response.data]
        assert plans_subtype_a.id in ids

    def test_each_plan_has_required_fields(self, plans_subtype_a):
        """Cada plan expone id, name, price, plans_type_name y activity_subtypes."""
        client = APIClient()
        response = client.get(reverse(self.URL))
        plan = next(p for p in response.data if p['id'] == plans_subtype_a.id)
        for field in ['id', 'name', 'plans_type_name', 'activity_subtypes']:
            assert field in plan, f"Campo '{field}' faltante en la respuesta"
        assert 'price' not in plan

    def test_activity_subtypes_nested_in_plan(self, plans_subtype_a, activity_subtype):
        """
        Las subactividades del tipo padre se anidan dentro del plan.
        'activity_subtype' del conftest tiene plans_type=plans_type, que es
        el padre de plans_subtype_a.
        """
        client = APIClient()
        response = client.get(reverse(self.URL))
        plan = next(p for p in response.data if p['id'] == plans_subtype_a.id)
        ids = [a['id'] for a in plan['activity_subtypes']]
        assert activity_subtype.id in ids

    def test_activity_subtype_includes_activity_type_name(self, plans_subtype_a, activity_subtype):
        """Cada subactividad expone activity_type_name (nombre de la disciplina)."""
        client = APIClient()
        response = client.get(reverse(self.URL))
        plan = next(p for p in response.data if p['id'] == plans_subtype_a.id)
        act = next(a for a in plan['activity_subtypes'] if a['id'] == activity_subtype.id)
        assert 'activity_type_name' in act
        assert act['activity_type_name'] == activity_subtype.activity_type.name

    def test_deleted_plan_subtype_excluded(self, plans_subtype_a):
        """Un PlansSubtype eliminado (soft delete) no aparece en /prices/."""
        plans_subtype_a.delete()
        client = APIClient()
        response = client.get(reverse(self.URL))
        ids = [p['id'] for p in response.data]
        assert plans_subtype_a.id not in ids

    def test_deleted_activity_subtype_excluded(self, plans_subtype_a, activity_subtype):
        """
        Una subactividad eliminada no aparece en los activity_subtypes del plan.
        El filtro deleted__isnull=True se aplica al fetch de subactividades.
        """
        activity_subtype.delete()
        client = APIClient()
        response = client.get(reverse(self.URL))
        plan = next((p for p in response.data if p['id'] == plans_subtype_a.id), None)
        if plan:
            ids = [a['id'] for a in plan['activity_subtypes']]
            assert activity_subtype.id not in ids


# PricesViewSet.combo_preview

@pytest.mark.django_db
class TestPricesComboPreview:
    """ el descuento del preview se aplica por PaymentMethod (final_amount),
    no sobre los campos legacy price_cash/price_transfer."""
    URL = 'prices-combo-preview'

    def _get(self, ids):
        client = APIClient()
        return client.get(reverse(self.URL), {'plans': ','.join(str(i) for i in ids)})

    def test_new_pricing_returns_final_amount_per_method(
        self, plans_subtype_a, plans_subtype_b, combo_plan_discount
    ):
        # Planes solo-nuevos: precio cargado en PaymentMethod, price_cash/transfer None.
        PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        PaymentMethod.objects.create(amount='6000', method='Transferencia', plans_subtype=plans_subtype_a)
        PaymentMethod.objects.create(amount='8000', method='Efectivo', plans_subtype=plans_subtype_b)

        resp = self._get([plans_subtype_a.id, plans_subtype_b.id])
        assert resp.status_code == 200, resp.data

        plans = {p['id']: p for p in resp.data['plans']}
        pa = plans[plans_subtype_a.id]
        assert pa['discount_pct'] == Decimal('10.00')
        finals_a = {pm['method']: pm['final_amount'] for pm in pa['payment_methods']}
        assert finals_a['Efectivo'] == '4500.00'       # 5000 * 0.90
        assert finals_a['Transferencia'] == '5400.00'  # 6000 * 0.90

        pb = plans[plans_subtype_b.id]
        finals_b = {pm['method']: pm['final_amount'] for pm in pb['payment_methods']}
        assert finals_b['Efectivo'] == '7200.00'       # 8000 * 0.90

    def test_legacy_price_fields_absent(
        self, plans_subtype_a, plans_subtype_b, combo_plan_discount
    ):
        PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        resp = self._get([plans_subtype_a.id, plans_subtype_b.id])
        pa = next(p for p in resp.data['plans'] if p['id'] == plans_subtype_a.id)
        assert 'final_price_cash' not in pa
        assert 'final_price_transfer' not in pa
        # El precio con descuento sigue viniendo por método (fuente de verdad = PaymentMethod)
        finals = {pm['method']: pm['final_amount'] for pm in pa['payment_methods']}
        assert finals['Efectivo'] == '4500.00'  # 5000 * 0.90

    def test_no_combo_final_amount_equals_amount(self, plans_subtype_a):
        PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        resp = self._get([plans_subtype_a.id])
        pa = resp.data['plans'][0]
        assert pa['discount_pct'] == Decimal('0')
        assert pa['payment_methods'][0]['final_amount'] == '5000.00'

    def test_non_numeric_amount_final_is_none(
        self, plans_subtype_a, plans_subtype_b, combo_plan_discount
    ):
        PaymentMethod.objects.create(amount='a consultar', method='Efectivo', plans_subtype=plans_subtype_a)
        resp = self._get([plans_subtype_a.id, plans_subtype_b.id])
        pa = next(p for p in resp.data['plans'] if p['id'] == plans_subtype_a.id)
        assert pa['payment_methods'][0]['final_amount'] is None

    def test_plan_discount_reflected_in_preview(self, plans_subtype_a):
        from apps.plans_type.models import PlanDiscount
        from apps.payment_method.models import PaymentMethod
        PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        PlanDiscount.objects.create(plans_subtype=plans_subtype_a, discount_pct='20.00')
        resp = self._get([plans_subtype_a.id])
        pa = next(p for p in resp.data['plans'] if p['id'] == plans_subtype_a.id)
        assert pa['discount_pct'] == Decimal('20.00')
        finals = {pm['method']: pm['final_amount'] for pm in pa['payment_methods']}
        assert finals['Efectivo'] == '4000.00'  # 5000 * 0.80

    # applied_combos solo con match EXACTO

    def test_applied_combos_excluye_combo_parcial(self, plans_subtype_a, plans_subtype_b, combo_plan_discount):
        """Un combo A+B NO debe aparecer en applied_combos si la selección es A,B,C
        (coincidencia parcial)."""
        from apps.plans_subtype.models import PlansSubtype
        c = PlansSubtype.objects.create(name='C', plan_type=plans_subtype_a.plan_type)
        resp = self._get([plans_subtype_a.id, plans_subtype_b.id, c.id])
        assert resp.status_code == 200, resp.data
        combo_ids = [x['combo_id'] for x in resp.data['applied_combos']]
        assert combo_plan_discount.id not in combo_ids

    def test_applied_combos_incluye_combo_exacto(self, plans_subtype_a, plans_subtype_b, combo_plan_discount):
        """El combo A+B sí aparece cuando la selección es exactamente A,B."""
        resp = self._get([plans_subtype_a.id, plans_subtype_b.id])
        assert resp.status_code == 200, resp.data
        combo_ids = [x['combo_id'] for x in resp.data['applied_combos']]
        assert combo_plan_discount.id in combo_ids

    def test_descuento_por_plan_sigue_subset(self, plans_subtype_a, plans_subtype_b, combo_plan_discount):
        """El descuento por plan NO cambia con con A,B,C el combo A+B sigue
        aplicando su descuento a A y B (solo applied_combos es exacto)."""
        from apps.plans_subtype.models import PlansSubtype
        from apps.payment_method.models import PaymentMethod
        PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        c = PlansSubtype.objects.create(name='C', plan_type=plans_subtype_a.plan_type)
        resp = self._get([plans_subtype_a.id, plans_subtype_b.id, c.id])
        pa = next(p for p in resp.data['plans'] if p['id'] == plans_subtype_a.id)
        assert pa['discount_pct'] == Decimal('10.00')  # combo A+B sigue descontando A


@pytest.mark.django_db
class TestPlanDiscountModel:
    def test_soft_delete(self, plans_subtype_a):
        from apps.plans_type.models import PlanDiscount
        pd = PlanDiscount.objects.create(plans_subtype=plans_subtype_a, discount_pct='15.00')
        pd.delete()
        assert not PlanDiscount.objects.filter(pk=pd.pk).exists()
        assert PlanDiscount.all_objects.filter(pk=pd.pk).exists()


@pytest.mark.django_db
class TestPlanDiscountEndpoint:
    URL = 'plan-discount-list'

    def test_admin_creates_plan_discount(self, admin_client, plans_subtype_a):
        resp = admin_client.post(reverse(self.URL), data={
            'plans_subtype': plans_subtype_a.id, 'discount_pct': '20.00',
        }, format='json')
        assert resp.status_code == 201, resp.data
        assert resp.data['plans_subtype'] == plans_subtype_a.id
        assert resp.data['plans_subtype_name'] == plans_subtype_a.name

    def test_admin_lists(self, admin_client, plan_discount):
        resp = admin_client.get(reverse(self.URL))
        assert resp.status_code == 200
        ids = [r['id'] for r in resp.data]
        assert plan_discount.id in ids

    def test_duplicate_active_discount_returns_400(self, admin_client, plans_subtype_a):
        """No se puede crear un segundo descuento activo para el mismo plan."""
        from apps.plans_type.models import PlanDiscount
        PlanDiscount.objects.create(plans_subtype=plans_subtype_a, discount_pct='10.00')
        resp = admin_client.post(reverse(self.URL), data={
            'plans_subtype': plans_subtype_a.id, 'discount_pct': '20.00',
        }, format='json')
        assert resp.status_code == 400
        assert 'plans_subtype' in resp.data

    def test_editing_same_discount_is_allowed(self, admin_client, plans_subtype_a):
        """Editar el descuento existente (mismo plan) no debe chocar consigo mismo."""
        from apps.plans_type.models import PlanDiscount
        pd = PlanDiscount.objects.create(plans_subtype=plans_subtype_a, discount_pct='10.00')
        resp = admin_client.patch(
            reverse('plan-discount-detail', args=[pd.id]),
            data={'discount_pct': '15.00'}, format='json',
        )
        assert resp.status_code == 200
        assert resp.data['discount_pct'] == '15.00'

    def test_soft_deleted_does_not_block_new(self, admin_client, plans_subtype_a):
        """Un descuento dado de baja no impide crear uno nuevo para el mismo plan."""
        from apps.plans_type.models import PlanDiscount
        pd = PlanDiscount.objects.create(plans_subtype=plans_subtype_a, discount_pct='10.00')
        pd.delete()
        resp = admin_client.post(reverse(self.URL), data={
            'plans_subtype': plans_subtype_a.id, 'discount_pct': '20.00',
        }, format='json')
        assert resp.status_code == 201
