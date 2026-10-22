from rest_framework import serializers
from .models import PaymentMethod


class PaymentMethodSerializer(serializers.ModelSerializer):
    activity_subtype_name = serializers.SerializerMethodField()

    class Meta:
        model = PaymentMethod
        fields = '__all__'

    def get_activity_subtype_name(self, obj):
        ps = obj.plans_subtype
        if ps and ps.activity_subtype_id:
            return ps.activity_subtype.name
        return None

    def validate(self, data):
        def effective(field):
            # En un PATCH parcial DRF solo trae los campos enviados; para los
            # que no vinieron se usa el valor actual del registro (self.instance).
            # En create y en PUT completo se sigue exigiendo el campo (fallback None).
            if field in data:
                return data[field]
            if self.partial:
                return getattr(self.instance, field, None)
            return None

        if not effective('amount'):
            raise serializers.ValidationError({"amount": "El campo 'amount' es obligatorio."})
        if not effective('method'):
            raise serializers.ValidationError({"method": "El campo 'method' es obligatorio."})
        if not effective('plans_subtype'):
            raise serializers.ValidationError({"plans_subtype": "El campo 'plans_subtype' es obligatorio."})
        return data
