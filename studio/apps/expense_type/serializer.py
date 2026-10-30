from rest_framework import serializers
from .models import ExpenseType

class ExpenseTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseType
        fields = '__all__'

    def validate(self, data):
        # Verificar que el campo `name` no sea nulo ni vacío
        if not data.get('name'):
            raise serializers.ValidationError({"name": "El campo 'name' es obligatorio."})
        return data
