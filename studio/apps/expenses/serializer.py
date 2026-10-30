from rest_framework import serializers
from .models import Expense
from apps.expense_type.serializer import ExpenseTypeSerializer
from apps.expense_type.models import ExpenseType

class ExpenseSerializer(serializers.ModelSerializer):
    # PrimaryKeyRelatedField para el campo `type_id`, con filtrado de elementos eliminados
    type_id = serializers.PrimaryKeyRelatedField(
        queryset=ExpenseType.objects.filter(deleted__isnull=True),  # Filtrar solo tipos no eliminados
        source='type', 
        write_only=True
    )
    type = ExpenseTypeSerializer(read_only=True)  # Serializer anidado para mostrar el objeto completo

    class Meta:
        model = Expense
        fields = '__all__'

    def validate(self, data):
        # Verificar que los campos `amount`, `type` y `method` no sean nulos ni vacíos
        if data.get('amount') is None:
            raise serializers.ValidationError({"amount": "El campo 'amount' es obligatorio."})
        if not data.get('type'):
            raise serializers.ValidationError({"type": "El campo 'type' es obligatorio."})
        if not data.get('method'):
            raise serializers.ValidationError({"method": "El campo 'method' es obligatorio."})
        return data
