from rest_framework import serializers
from .models import Appointment
from apps.people.serializer import PersonSerializer
from apps.slots.serializer import SlotSerializer
from apps.people.models import Person
from apps.slots.models import Slot
from apps.sworn_statement.serializer import AppointmentSwornStatementInlineSerializer


class AppointmentSerializer(serializers.ModelSerializer):
    person_id = serializers.PrimaryKeyRelatedField(queryset=Person.objects.all(), source='person', write_only=True)
    person = PersonSerializer(read_only=True)
    slot_id = serializers.PrimaryKeyRelatedField(queryset=Slot.objects.all(), source='slot', write_only=True)
    slot = SlotSerializer(read_only=True)
    sworn_statements = AppointmentSwornStatementInlineSerializer(many=True, read_only=True)

    class Meta:
        model = Appointment
        fields = '__all__'
        read_only_fields = ['firmo_declaracion_clase', 'consumed_plan']


# Serializers para la vista de calendario

class CalendarAppointmentSerializer(serializers.ModelSerializer):
    """Reserva resumida para el calendario: solo lo que necesita mostrar el frontend."""
    person_id = serializers.IntegerField(source='person.id', read_only=True)
    person_name = serializers.SerializerMethodField()
    person_phone = serializers.CharField(source='person.phone', read_only=True, default=None)
    person_photo = serializers.SerializerMethodField()
    plan_sub_type = serializers.SerializerMethodField()
    exp_date = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            'id', 'person_id', 'person_name', 'person_phone', 'person_photo',
            'plan_sub_type', 'exp_date', 'reserved', 'created_at',
        ]

    def get_person_name(self, obj):
        if obj.person:
            return f"{obj.person.name} {obj.person.last_name}".strip()
        return None

    def _chosen_plan(self, obj):
        """Plan vigente (exp_date >= hoy) con sesiones (>0) del alumno, el de
        exp_date más lejano; None si no hay. Filtra en Python sobre active_plans
        (prefetch) para no hacer N+1."""
        from django.utils import timezone
        if not obj.person_id:
            return None
        today = timezone.now().date()
        vigentes = [
            p for p in obj.person.active_plans.all()
            if p.exp_date and p.exp_date >= today and (p.sessions_remaining or 0) > 0
        ]
        return max(vigentes, key=lambda p: p.exp_date) if vigentes else None

    def get_plan_sub_type(self, obj):
        plan = self._chosen_plan(obj)
        if plan and plan.plans_subtype_id:
            return {'id': plan.plans_subtype_id, 'name': plan.plans_subtype.name}
        return None

    def get_exp_date(self, obj):
        plan = self._chosen_plan(obj)
        return plan.exp_date.isoformat() if plan else None

    def get_person_photo(self, obj):
        request = self.context.get('request')
        if obj.person and obj.person.profile_photo:
            url = obj.person.profile_photo.url
            return request.build_absolute_uri(url) if request else url
        return None


class CalendarSlotSerializer(serializers.ModelSerializer):
    """Slot con sus reservas activas para el calendario."""
    room_name = serializers.CharField(source='room.name', read_only=True, default=None)
    studio_name = serializers.CharField(source='room.studio.name', read_only=True, default=None)
    activity = serializers.CharField(source='activity_subtype.name', read_only=True, default=None)
    status_name = serializers.CharField(source='status.name', read_only=True, default=None)
    week_day_name = serializers.SerializerMethodField()

    def get_week_day_name(self, obj):
        if not obj.date:
            return None
        days = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        return days[obj.date.weekday()]
    capacity = serializers.SerializerMethodField()
    appointments = serializers.SerializerMethodField()

    class Meta:
        model = Slot
        fields = [
            'id', 'date', 'start_time', 'end_time',
            'week_day_name', 'room_name', 'studio_name', 'activity',
            'availability', 'capacity', 'status_name',
            'appointments',
        ]

    def get_capacity(self, obj):
        # capacity = alumnos actuales + disponibilidad restante
        enrolled = obj.appointments.filter(deleted__isnull=True).count()
        avail = obj.availability or 0
        return enrolled + avail

    def get_appointments(self, obj):
        active = obj.appointments.filter(deleted__isnull=True).select_related('person').prefetch_related(
            'person__active_plans__plans_subtype'
        )
        return CalendarAppointmentSerializer(active, many=True, context=self.context).data