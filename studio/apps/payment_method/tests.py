import pytest
from django.urls import reverse
from .models import PaymentMethod


@pytest.mark.django_db
class TestPaymentMethodSoftDelete:

    def test_delete_sets_deleted(self, plans_subtype_a):
        pm = PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        pm.delete()
        pm.refresh_from_db()
        assert pm.deleted is not None

    def test_objects_hides_deleted(self, plans_subtype_a):
        pm = PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        pm.delete()
        assert not PaymentMethod.objects.filter(pk=pm.pk).exists()

    def test_all_objects_includes_deleted(self, plans_subtype_a):
        pm = PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        pm.delete()
        assert PaymentMethod.all_objects.filter(pk=pm.pk).exists()

    def test_all_objects_dead_returns_deleted(self, plans_subtype_a):
        pm = PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        pm.delete()
        assert PaymentMethod.all_objects.dead().filter(pk=pm.pk).exists()

    def test_all_objects_alive_excludes_deleted(self, plans_subtype_a):
        pm = PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        pm.delete()
        assert not PaymentMethod.all_objects.alive().filter(pk=pm.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user, plans_subtype_a):
        pm = PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        pm.delete()
        qs = PaymentMethod.all_objects.for_user(admin_user)
        assert qs.filter(pk=pm.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user, plans_subtype_a):
        pm = PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        pm.delete()
        qs = PaymentMethod.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=pm.pk).exists()

    def test_restore(self, plans_subtype_a):
        pm = PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        pm.delete()
        pm.restore()
        pm.refresh_from_db()
        assert pm.deleted is None

    def test_hard_delete_removes_from_db(self, plans_subtype_a):
        pm = PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        pk = pm.pk
        pm.hard_delete()
        assert not PaymentMethod.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestPaymentMethodViewForUser:
    URL = 'payments-list'

    def test_admin_list_includes_deleted(self, admin_client, plans_subtype_a):
        pm = PaymentMethod.objects.create(amount='6000', method='Transferencia', plans_subtype=plans_subtype_a)
        pm.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert pm.id in ids

    def test_consultor_list_excludes_deleted(self, consultor_client, plans_subtype_a):
        pm = PaymentMethod.objects.create(amount='6000', method='Transferencia', plans_subtype=plans_subtype_a)
        pm.delete()
        response = consultor_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert pm.id not in ids

    def test_delete_endpoint_is_soft_delete(self, admin_client, plans_subtype_a):
        pm = PaymentMethod.objects.create(amount='7000', method='Debito', plans_subtype=plans_subtype_a)
        url = reverse('payments-detail', args=[pm.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert PaymentMethod.all_objects.filter(pk=pm.pk).exists()
        pm.refresh_from_db()
        assert pm.deleted is not None


@pytest.mark.django_db
class TestPaymentMethodPlansSubtype:
    """ PaymentMethod apunta a plans_subtype y expone la subactividad."""
    URL = 'payments-list'

    def test_create_with_plans_subtype_returns_201_and_subactividad(self, admin_client, plans_subtype_a):
        resp = admin_client.post(reverse(self.URL), data={
            'amount': '5000', 'method': 'Efectivo', 'plans_subtype': plans_subtype_a.id,
        }, format='json')
        assert resp.status_code == 201, resp.data
        assert resp.data['plans_subtype'] == plans_subtype_a.id
        assert resp.data['activity_subtype_name'] == plans_subtype_a.activity_subtype.name

    def test_duplicate_plans_subtype_method_returns_400(self, admin_client, plans_subtype_a):
        admin_client.post(reverse(self.URL), data={
            'amount': '5000', 'method': 'Efectivo', 'plans_subtype': plans_subtype_a.id,
        }, format='json')
        resp = admin_client.post(reverse(self.URL), data={
            'amount': '6000', 'method': 'efectivo', 'plans_subtype': plans_subtype_a.id,
        }, format='json')
        assert resp.status_code == 400, resp.data

    def test_create_without_plans_subtype_returns_400(self, admin_client):
        resp = admin_client.post(reverse(self.URL), data={
            'amount': '5000', 'method': 'Efectivo',
        }, format='json')
        assert resp.status_code == 400, resp.data

    def test_model_has_no_plan_field(self):
        from django.core.exceptions import FieldDoesNotExist
        with pytest.raises(FieldDoesNotExist):
            PaymentMethod._meta.get_field('plan')


@pytest.mark.django_db
class TestPaymentMethodPartialUpdate:
    """ editar solo el precio (amount) de un metodo existente via PATCH parcial."""
    URL = 'payments-list'

    def test_patch_only_amount_returns_200_and_persists(self, admin_client, plans_subtype_a):
        pm = PaymentMethod.objects.create(
            amount='5000', method='Efectivo', plans_subtype=plans_subtype_a
        )
        url = reverse('payments-detail', args=[pm.pk])
        resp = admin_client.patch(url, data={'amount': '7500'}, format='json')
        assert resp.status_code == 200, resp.data
        pm.refresh_from_db()
        assert pm.amount == '7500'
        assert pm.method == 'Efectivo'
        assert pm.plans_subtype_id == plans_subtype_a.id

    def test_patch_blank_amount_returns_400(self, admin_client, plans_subtype_a):
        pm = PaymentMethod.objects.create(
            amount='5000', method='Efectivo', plans_subtype=plans_subtype_a
        )
        url = reverse('payments-detail', args=[pm.pk])
        resp = admin_client.patch(url, data={'amount': None}, format='json')
        assert resp.status_code == 400, resp.data

    def test_create_without_method_returns_400(self, admin_client, plans_subtype_a):
        resp = admin_client.post(reverse(self.URL), data={
            'amount': '5000', 'plans_subtype': plans_subtype_a.id,
        }, format='json')
        assert resp.status_code == 400, resp.data

    def test_put_omitting_field_returns_400(self, admin_client, plans_subtype_a):
        # PUT completo: omitir un campo obligatorio sigue dando 400 (no es parcial).
        pm = PaymentMethod.objects.create(
            amount='5000', method='Efectivo', plans_subtype=plans_subtype_a
        )
        url = reverse('payments-detail', args=[pm.pk])
        resp = admin_client.put(url, data={'method': 'Transferencia'}, format='json')
        assert resp.status_code == 400, resp.data
