from rest_framework import serializers
from .models import Hour
from apps.teachers.models import Teacher
from apps.teachers.serializer import TeacherSerializer

class HourSerializer(serializers.ModelSerializer):
    teacher_id = serializers.PrimaryKeyRelatedField(
        queryset=Teacher.objects.all(),
        source='teacher',
        write_only=True
    )
    teacher = TeacherSerializer(read_only=True)  # Mostrar detalles del teacher

    class Meta:
        model = Hour
        fields = ['id', 'teacher_id', 'teacher', 'month', 'hour', 'extra_hour', 'total', 'left', 'deleted']

    def validate(self, data):
        # Validar que los campos obligatorios no sean nulos o vacíos
        required_fields = ['teacher', 'month', 'hour', 'total']
        for field in required_fields:
            if field not in data or not data[field]:
                raise serializers.ValidationError({field: f"El campo {field} es obligatorio."})
        return data
