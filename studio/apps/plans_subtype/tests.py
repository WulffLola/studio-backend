import pytest
from apps.plans_subtype.serializer import PlansSubtypeSerializer
from apps.payment_method.models import PaymentMethod


@pytest.mark.django_db
class TestPlansSubtypePaymentMethods:
    """ un plan expone sus N métodos de pago con precio (PaymentMethod)."""

    def test_serializer_lists_payment_methods(self, plans_subtype_a):
        PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        PaymentMethod.objects.create(amount='5500', method='Transferencia', plans_subtype=plans_subtype_a)
        data = PlansSubtypeSerializer(plans_subtype_a).data
        assert 'payment_methods' in data
        by_method = {pm['method']: pm['amount'] for pm in data['payment_methods']}
        assert by_method == {'Efectivo': '5000', 'Transferencia': '5500'}

    def test_deleted_payment_method_excluded(self, plans_subtype_a):
        pm = PaymentMethod.objects.create(amount='5000', method='Efectivo', plans_subtype=plans_subtype_a)
        pm.delete()
        data = PlansSubtypeSerializer(plans_subtype_a).data
        assert data['payment_methods'] == []
