from rest_framework import serializers
from .models import TeachersTurn
from apps.teachers.serializer import TeacherSerializer
from apps.slots.serializer import SlotSerializer
from apps.teachers.models import Teacher
from apps.slots.models import Slot
from apps.teacher_rol.models import Rol
from apps.teacher_rol.serializer import RolSerializer

class TeachersTurnSerializer(serializers.ModelSerializer):
    teacher = TeacherSerializer(read_only=True)  # Usamos el serializer completo de Teacher
    slot = SlotSerializer(read_only=True)        # Usamos el serializer completo de Slot
    teacher_id = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.all(), write_only=True, source='teacher')
    slot_id = serializers.PrimaryKeyRelatedField(queryset=Slot.objects.all(), write_only=True, source='slot')



    class Meta:
        model = TeachersTurn
        fields = ['id', 'teacher', 'slot', 'teacher_id', 'slot_id', 'rol', 'created_at', 'updated_at', 'deleted']

    def validate(self, data):
        slot = data.get('slot')
        #is_receptionist = data.get('is_receptionist')
        rol = data.get('rol')

        # Contar cuántos profesores están asignados al mismo slot
        same_slot_teachers = TeachersTurn.objects.filter(slot=slot, deleted__isnull=True)

        if same_slot_teachers.count() >= 3:
            raise serializers.ValidationError("Ya hay tres profesores asignados a este slot.")

        # Verificar que no haya dos recepcionistas o dos no recepcionistas en el mismo slot
        if same_slot_teachers.filter(rol__iexact=rol).exists():
            raise serializers.ValidationError(f"Ya existe un profesor con el rol '{rol}' en este slot.")

        return data