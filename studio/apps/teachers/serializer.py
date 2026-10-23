from rest_framework import serializers
from .models import Teacher

class TeacherSerializer(serializers.ModelSerializer):


    class Meta:
        model = Teacher
        fields = '__all__'

    def validate(self, data):
            # Verificar que los campos obligatorios no estén vacíos
            required_fields = ['name', 'last_name', 'sex', 'dni', 'email', 'phone', 'birth_date']
            for field in required_fields:
                if not data.get(field):
                    raise serializers.ValidationError({field: f'El campo {field} no puede estar vacío.'})
            return data