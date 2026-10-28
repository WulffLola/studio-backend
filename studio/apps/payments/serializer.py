from rest_framework import serializers
from .models import Payment, PaymentItem
from apps.people.models import Person
from apps.people.serializer import PersonSerializer
from apps.plans_subtype.models import PlansSubtype
from apps.plans_subtype.serializer import PlansSubtypeSerializer
from datetime import datetime


class PaymentItemInlineSerializer(serializers.ModelSerializer):
    """Serializer liviano para mostrar ítems dentro de un Payment."""
    plans_subtype = PlansSubtypeSerializer(read_only=True)

    class Meta:
        model = PaymentItem
        fields = ['id', 'plans_subtype', 'base_amount', 'discount_pct', 'final_amount']


class PaymentSerializer(serializers.ModelSerializer):
    person_id = serializers.PrimaryKeyRelatedField(queryset=Person.objects.all(), source='person', write_only=True)
    person = PersonSerializer(read_only=True)
    items = PaymentItemInlineSerializer(many=True, read_only=True)

    class Meta:
        model = Payment
        fields = '__all__'

    def validate_date(self, value):
        input_date = self.initial_data.get('date')
        try:
            datetime.strptime(input_date, "%Y-%m-%dT%H:%M:%S")
        except (ValueError, TypeError):
            raise serializers.ValidationError(
                "Invalid format. Use 'YYYY-MM-DDTHH:MM:SS' instead"
            )
        return value


class PaymentItemSerializer(serializers.ModelSerializer):
    plans_subtype = PlansSubtypeSerializer(read_only=True)
    plans_subtype_id = serializers.PrimaryKeyRelatedField(
        queryset=PlansSubtype.objects.all(), source='plans_subtype', write_only=True
    )
    person_id = serializers.PrimaryKeyRelatedField(
        queryset=Person.objects.all(), source='person', write_only=True, required=False, allow_null=True
    )
    person = PersonSerializer(read_only=True)

    class Meta:
        model = PaymentItem
        fields = '__all__'
        read_only_fields = ['final_amount']
