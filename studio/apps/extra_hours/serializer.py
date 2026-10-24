from rest_framework import serializers
from .models import ExtraHours
from apps.teachers.serializer import TeacherSerializer
from apps.slots.serializer import SlotSerializer
from apps.teachers.models import Teacher
from apps.slots.models import Slot

class ExtraHoursSerializer(serializers.ModelSerializer):
    teacher_id = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.all(), source='teacher', write_only=True)
    teacher = TeacherSerializer(read_only=True)
    slot_id = serializers.PrimaryKeyRelatedField(queryset=Slot.objects.all(), source='slot', write_only=True)
    slot = SlotSerializer(read_only=True)

    class Meta:
        model = ExtraHours
        fields = ['id', 'teacher_id', 'teacher', 'slot_id', 'slot', 'price', 'deleted']

    def validate(self, data):
        if not data.get('teacher'):
            raise serializers.ValidationError({"teacher_id": "El campo 'teacher_id' es obligatorio."})
        if not data.get('slot'):
            raise serializers.ValidationError({"slot_id": "El campo 'slot_id' es obligatorio."})
        return data