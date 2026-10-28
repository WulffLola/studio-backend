from rest_framework import serializers
from .models import Slot, SlotTemplate, FixedSlot
from apps.weeks.serializer import WeekSerializer
from apps. status.serializer import StatusSerializer
from apps.status.models import Status
from apps.weeks.models import Week


class StartEndTimeValidationMixin:
    """Valida que end_time sea posterior a start_time.

    Resuelve los valores faltantes contra la instancia para soportar
    actualizaciones parciales (PATCH) donde solo se envía uno de los dos.
    """

    def validate(self, attrs):
        attrs = super().validate(attrs)
        start = attrs.get('start_time')
        end = attrs.get('end_time')
        if self.instance is not None:
            if start is None:
                start = getattr(self.instance, 'start_time', None)
            if end is None:
                end = getattr(self.instance, 'end_time', None)
        if start and end and end <= start:
            raise serializers.ValidationError(
                {'end_time': 'end_time debe ser posterior a start_time.'}
            )
        return attrs


class SlotTemplateSerializer(StartEndTimeValidationMixin, serializers.ModelSerializer):
    days_of_week = WeekSerializer(many=True, read_only=True)
    days_of_week_ids = serializers.PrimaryKeyRelatedField(
        queryset=Week.objects.all(), source='days_of_week', many=True, write_only=True
    )

    class Meta:
        model = SlotTemplate
        fields = '__all__'


class SlotSerializer(StartEndTimeValidationMixin, serializers.ModelSerializer):
    status = StatusSerializer(read_only=True)
    status_id = serializers.PrimaryKeyRelatedField(queryset=Status.objects.all(), source='status', write_only=True, required=False)
    template_id = serializers.IntegerField(source='template.id', read_only=True, allow_null=True)
    teachers = serializers.SerializerMethodField(read_only=True)
    # week_day_name = serializers.SerializerMethodField()

    class Meta:
        model = Slot
        fields = '__all__'
        extra_kwargs = {'template': {'write_only': True}}

    def get_teachers(self, obj):
        """Docentes asignados al slot vía teachers_turn.

        Lista de {rol, teacher:{id,name,last_name}} por cada asignación viva
        (excluye soft-deleted). `teacher` puede ser None (el modelo lo permite).
        Itera el default manager (`obj.teachers_turn.all()`, ya sin eliminados) y
        filtra en Python para aprovechar el prefetch de los viewsets y no disparar
        una query por slot. [] si no hay ninguna."""
        return [
            {
                'rol': tt.rol,
                'teacher': (
                    {'id': tt.teacher.id, 'name': tt.teacher.name, 'last_name': tt.teacher.last_name}
                    if tt.teacher_id else None
                ),
            }
            for tt in obj.teachers_turn.all()
            if tt.deleted is None
        ]

    # def get_week_day_name(self, obj):
    # if not obj.date:
    # return None
    # days = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    # return days[obj.date.weekday()]

class FixedSlotSerializer(serializers.ModelSerializer):
    template = SlotTemplateSerializer(read_only=True)
    template_id = serializers.PrimaryKeyRelatedField(
        queryset=SlotTemplate.objects.all(), source='template', write_only=True
    )
    reservas_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = FixedSlot
        fields = '__all__'
        read_only_fields = ['created_at']

    def get_reservas_count(self, obj):
        """Cantidad de reservas (Appointment) activas del alumno en Slots de este
        template dentro de la vigencia del turno fijo (visualización,."""
        from apps.appointments.models import Appointment
        qs = Appointment.objects.filter(
            person=obj.person,
            slot__template=obj.template,
            slot__date__gte=obj.start_date,
            deleted__isnull=True,
        )
        if obj.end_date is not None:
            qs = qs.filter(slot__date__lte=obj.end_date)
        return qs.count()

    def validate(self, attrs):
        attrs = super().validate(attrs)

        # --- Check existente: end_date >= start_date ---
        start = attrs.get('start_date')
        end = attrs.get('end_date')
        if self.instance is not None:
            if start is None:
                start = self.instance.start_date
            if end is None:
                end = self.instance.end_date
        if start and end and end < start:
            raise serializers.ValidationError(
                {'end_date': 'end_date debe ser posterior o igual a start_date.'}
            )

        # --- Check de solapamiento de turnos fijos ---
        person = attrs.get('person')
        new_template = attrs.get('template')
        new_start_date = attrs.get('start_date')
        new_end_date = attrs.get('end_date')

        if self.instance is not None:
            if person is None:
                person = self.instance.person
            if new_template is None:
                new_template = self.instance.template
            if new_start_date is None:
                new_start_date = self.instance.start_date
            if new_end_date is None:
                new_end_date = self.instance.end_date

        if person and new_template:
            new_days = set(new_template.days_of_week.values_list('id', flat=True))

            existing_qs = FixedSlot.objects.filter(person=person)
            if self.instance is not None:
                existing_qs = existing_qs.exclude(pk=self.instance.pk)

            for fs in existing_qs.select_related('template').prefetch_related('template__days_of_week'):
                ex_template = fs.template
                # .all() usa el caché del prefetch_related (values_list dispararía una query por iteración)
                ex_days = {d.id for d in ex_template.days_of_week.all()}

                # 1. Comparten al menos un día de la semana?
                if not new_days.intersection(ex_days):
                    continue

                # 2. Los horarios [start_time, end_time) se solapan?
                if not (new_template.start_time < ex_template.end_time and
                        ex_template.start_time < new_template.end_time):
                    continue

                # 3. Los períodos de vigencia [start_date, end_date] se solapan?
                # No solapan si: el nuevo termina antes de que el existente empiece
                if new_end_date is not None and new_end_date < fs.start_date:
                    continue
                # No solapan si: el existente termina antes de que el nuevo empiece
                if fs.end_date is not None and new_start_date is not None and fs.end_date < new_start_date:
                    continue

                raise serializers.ValidationError({
                    'template_id': (
                        f'El turno fijo se solapa con otro turno activo de la misma persona '
                        f'(día compartido, horario {ex_template.start_time:%H:%M}–{ex_template.end_time:%H:%M}).'
                    )
                })

        return attrs

    def create(self, validated_data):
        # Restaurar/reutilizar: si el (person, template) ya existe pero está
        # soft-deleted, se revive esa misma fila en lugar de insertar otra (el
        # unique_together la rechazaría con IntegrityError). Depende de que `objects`
        # (solo activos) sea el default manager de FixedSlot: así el
        # UniqueTogetherValidator de DRF no ve la fila muerta y el alta cae acá.
        # No reordenar los managers.
        person = validated_data['person']
        template = validated_data['template']
        existing = FixedSlot.all_objects.filter(
            person=person, template=template, deleted__isnull=False,
        ).first()
        if existing is not None:
            existing.deleted = None
            existing.start_date = validated_data['start_date']
            existing.end_date = validated_data.get('end_date')
            existing.observation = validated_data.get('observation', '')
            existing.save()
            return existing
        return super().create(validated_data)
