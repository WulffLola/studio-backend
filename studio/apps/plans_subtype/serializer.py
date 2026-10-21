from rest_framework import serializers
from .models import PlansSubtype
from apps.plans_type.serializer import PlansTypeSerializer


def _serialize_payment_methods(obj):
    """Métodos de pago (precio por método) vivos del plan. Fuente de verdad
    de precios = PaymentMethod. Usa el prefetch `alive_payment_methods`
    cuando está disponible; si no, filtra directo."""
    pms = getattr(obj, 'alive_payment_methods', None)
    if pms is None:
        pms = obj.payment_methods.filter(deleted__isnull=True)
    return [
        {'id': pm.id, 'method': pm.method, 'amount': pm.amount}
        for pm in pms
    ]


class PlansSubtypeSerializer(serializers.ModelSerializer):
    plans_type_name = serializers.CharField(source='plan_type.name', read_only=True)
    activity_subtype_name = serializers.CharField(source='activity_subtype.name', read_only=True, allow_null=True)
    payment_methods = serializers.SerializerMethodField()

    class Meta:
        model = PlansSubtype
        fields = '__all__'

    def get_payment_methods(self, obj):
        return _serialize_payment_methods(obj)


class ActivitySubtypeInPriceSerializer(serializers.Serializer):
    """
    Serializer liviano para exponer subactividades dentro de un plan.
    No usa ModelSerializer para evitar import circular con activity_subtype.
    """
    id = serializers.IntegerField()
    name = serializers.CharField()
    activity_type_name = serializers.SerializerMethodField()

    def get_activity_type_name(self, obj):
        return obj.activity_type.name if obj.activity_type_id else None


class PlansSubtypePublicSerializer(serializers.ModelSerializer):
    """
    Vista pública de un plan concreto.
    Incluye el nombre del tipo padre, los métodos de pago con precio y la subactividad que cubre.
    """
    plans_type_name = serializers.CharField(source='plan_type.name', read_only=True)
    payment_methods = serializers.SerializerMethodField()
    activity_subtypes = serializers.SerializerMethodField()

    class Meta:
        model = PlansSubtype
        fields = ['id', 'name', 'plans_type_name', 'payment_methods', 'activity_subtypes']

    def get_payment_methods(self, obj):
        return _serialize_payment_methods(obj)

    def get_activity_subtypes(self, obj):
        # Cada PlansSubtype ahora tiene su propio activity_subtype directamente.
        if obj.activity_subtype_id:
            return ActivitySubtypeInPriceSerializer([obj.activity_subtype], many=True).data
        return []
