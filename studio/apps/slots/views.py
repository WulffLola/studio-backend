
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .serializer import SlotSerializer, SlotTemplateSerializer, FixedSlotSerializer
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import transaction
from .models import Slot, SlotTemplate, FixedSlot
from .services import generate_slots_for_template, capacity_exceeded_message
from apps.appointments.models import Appointment
from apps.holidays.services import holiday_dates_in_range
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper, StudentReadMixin
from apps.actions.models import Action
from apps.teachers_turn.selectors import teachers_turn_prefetch

# Mapeo canónico Python weekday() -> nombre en español usado en el modelo Week
# 0=Monday … 6=Sunday
WEEKDAY_NAMES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

MIN_GENERATION_MONTHS = 3


def capacity_error(availability, room_id):
    """
    Valida la disponibilidad (`availability`) de un slot.

    Devuelve un Response 400 si: no es un entero válido, es negativa, o supera la
    capacidad de la sala; None si no hay restricción que aplicar. Envuelve la lógica
    compartida `capacity_exceeded_message` (services), single source of truth
    reutilizado en creación/edición de slots, templates y generación.
    """
    msg = capacity_exceeded_message(availability, room_id)
    if msg:
        return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)
    return None


class SlotsViewSet(StudentReadMixin, viewsets.ModelViewSet):
    queryset = Slot.objects.all()
    serializer_class = SlotSerializer
    write_permission = IsAdministrador | IsConsultor | IsSuper

    def get_queryset(self):
        qs = Slot.all_objects.for_user(self.request.user)
        # precargar las asignaciones vivas de docentes (teachers_turn) para
        # que SlotSerializer.get_teachers no dispare N+1 (una query por slot).
        qs = qs.prefetch_related(teachers_turn_prefetch())
        date_from = self.request.query_params.get('date_from')
        date_to   = self.request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        return qs

    def create(self, request, *args, **kwargs):
        slot_date_str = request.data.get('date')
        start_time = request.data.get('start_time')
        template_id = request.data.get('template')

        if slot_date_str and start_time:
            # Duplicado: misma fecha + hora + sala (cross-template)
            room_id = request.data.get('room')
            dup_qs = Slot.objects.filter(date=slot_date_str, start_time=start_time, deleted__isnull=True)
            if room_id:
                dup_qs = dup_qs.filter(room_id=room_id)
            if dup_qs.exists():
                return Response(
                    {"detail": "Ya existe un slot en esa fecha, hora y sala."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Validar que la fecha corresponda a un día activo del template (si se provee)
        if slot_date_str and template_id:
            try:
                slot_date = date.fromisoformat(slot_date_str)
                template = SlotTemplate.objects.get(pk=template_id, is_active=True)
                template_day_names = set(template.days_of_week.values_list('day', flat=True))
                if WEEKDAY_NAMES[slot_date.weekday()] not in template_day_names:
                    return Response(
                        {"detail": f"La fecha {slot_date_str} es un {WEEKDAY_NAMES[slot_date.weekday()]} "
                                   f"y no coincide con los días del template ({', '.join(sorted(template_day_names))})."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except SlotTemplate.DoesNotExist:
                return Response(
                    {"detail": "Template no encontrado o inactivo."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except ValueError:
                pass  # fecha inválida — el serializer lo capturará

        # Validar que availability no supere la capacidad de la sala
        err = capacity_error(request.data.get('availability'), request.data.get('room'))
        if err:
            return err

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        slot = self.get_object()

        if Appointment.objects.filter(slot=slot, deleted__isnull=True).exists():
            return Response(
                {"detail": "No se puede modificar el slot porque ya está en uso en un appointment."},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = request.data.copy()

        # Validar disponibilidad (no numérica / negativa / capacidad) antes de usarla
        raw_availability = data.get('availability', slot.availability)
        err = capacity_error(raw_availability, data.get('room', slot.room_id))
        if err:
            return err

        # Auto-gestión de status según disponibilidad, solo si hay un valor
        # numérico (availability/status del slot pueden ser NULL). Se escribe la
        # key 'status_id' (el campo escribible del serializer; 'status' es
        # read_only y se descartaba en silencio).
        if raw_availability is not None:
            new_availability = int(raw_availability)
            data['availability'] = new_availability
            data['status_id'] = 1 if new_availability > 0 else 2

        serializer = self.get_serializer(slot, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        slot = self.get_object()

        if Appointment.objects.filter(slot=slot, deleted__isnull=True).exists():
            return Response(
                {"detail": "No se puede eliminar el slot porque ya está en uso en un appointment."},
                status=status.HTTP_400_BAD_REQUEST
            )

        slot.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """Restaura un slot dado de baja (p. ej. cancelado por feriado). No permite
        restaurar en una fecha que sigue siendo feriado.

        Se resuelve contra ``all_objects`` (no ``get_object()``/``for_user``, que
        para roles no-admin oculta los borrados) y se validan permisos a mano. El
        gate de rol lo aplica StudentReadMixin.get_permissions (acción de escritura).
        """
        slot = get_object_or_404(Slot.all_objects, pk=pk)
        self.check_object_permissions(request, slot)

        if slot.deleted is None:
            return Response(
                {"detail": "El slot no está eliminado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if slot.date and holiday_dates_in_range(slot.date, slot.date):
            return Response(
                {"detail": "No se puede restaurar un slot en una fecha de feriado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        slot.restore()
        return Response(self.get_serializer(slot).data, status=status.HTTP_200_OK)


class SlotTemplateViewSet(viewsets.ModelViewSet):
    """CRUD de templates de recurrencia."""
    queryset = SlotTemplate.objects.all()
    serializer_class = SlotTemplateSerializer
    permission_classes = [IsAdministrador | IsSuper]

    def _validate_room_capacity(self, request, instance=None):
        availability = request.data.get('availability')
        room_id = request.data.get('room')
        if availability is None and instance:
            availability = instance.availability
        if room_id is None and instance:
            room_id = instance.room_id
        return capacity_error(availability, room_id)

    def create(self, request, *args, **kwargs):
        err = self._validate_room_capacity(request)
        if err:
            return err
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        err = self._validate_room_capacity(request, instance)
        if err:
            return err
        return super().update(request, *args, **kwargs)


class SlotGenerationViewSet(viewsets.ViewSet):
    """
    Genera Slot individuales (occurrences) a partir de un SlotTemplate
    para un rango de fechas concreto.

    Body esperado:
        template_id  : int
        date_from    : "YYYY-MM-DD"
        date_to      : "YYYY-MM-DD"
    """
    permission_classes = [IsAdministrador | IsSuper]

    def create(self, request, *args, **kwargs):
        template_id = request.data.get('template_id')
        date_from_str = request.data.get('date_from')
        date_to_str = request.data.get('date_to')

        if not template_id:
            return Response(
                {"detail": "Campos requeridos: template_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Si no se proveen fechas, usar hoy -> hoy + MIN_GENERATION_MONTHS
        today = date.today()
        if not date_from_str:
            date_from_str = today.isoformat()
        if not date_to_str:
            date_to_str = (today + relativedelta(months=MIN_GENERATION_MONTHS)).isoformat()

        try:
            template = SlotTemplate.objects.get(pk=template_id)
        except SlotTemplate.DoesNotExist:
            return Response({"detail": "Template no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if not template.is_active:
            return Response({"detail": "El template está inactivo y no puede generar slots."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            date_from = date.fromisoformat(date_from_str)
            date_to = date.fromisoformat(date_to_str)
        except ValueError:
            return Response({"detail": "Formato de fecha inválido. Usar YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        if date_from > date_to:
            return Response({"detail": "date_from debe ser anterior a date_to."}, status=status.HTTP_400_BAD_REQUEST)

        # Ventana mínima: date_to debe cubrir al menos 3 meses desde hoy
        min_date_to = today + relativedelta(months=MIN_GENERATION_MONTHS)
        if date_to < min_date_to:
            return Response(
                {"detail": f"date_to debe ser al menos {min_date_to.isoformat()} "
                           f"({MIN_GENERATION_MONTHS} meses desde hoy)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validar capacidad de sala: la sala pudo reducir su capacidad después
        # de crear el template. No generar nada si la disponibilidad la excede.
        err = capacity_error(template.availability, template.room_id)
        if err:
            return err

        # La generación (feriados + loop + forward-reservation + audit) vive en el
        # service, compartida con el command generate_slots.
        summary = generate_slots_for_template(
            template, date_from, date_to, user=request.user,
        )

        return Response({
            "detail": f"{summary['created']} slots generados, "
                      f"{summary['skipped']} omitidos (ya existían), "
                      f"{summary['feriados_omitidos']} omitidos por feriado.",
            "reservas_automaticas": summary["reservas_automaticas"],
            "warnings": summary["warnings"],
            "feriados_omitidos": summary["feriados_omitidos"],
            "slots_cancelados": summary["slots_cancelados"],
            "slots_protegidos": summary["slots_protegidos"],
        }, status=status.HTTP_201_CREATED)


class AvailableSlot(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet to retrieve all slots with status 1, ordered by day and time.
    """
    serializer_class = SlotSerializer
    permission_classes = [IsAdministrador | IsSuper | IsConsultor]

    def get_queryset(self):
        today = date.today()
        return Slot.objects.filter(
            status_id=1,
            deleted__isnull=True,
            date__gte=today,
        ).order_by('date', 'start_time')


class FixedSlotViewSet(StudentReadMixin, viewsets.ModelViewSet):
    """
    CRUD de turnos fijos. Permite asociar una persona a un SlotTemplate recurrente.
    Filtros: ?person=<id>  ?template=<id>
    """
    serializer_class = FixedSlotSerializer
    write_permission = IsAdministrador | IsConsultor | IsSuper

    def get_queryset(self):
        qs = FixedSlot.all_objects.for_user(self.request.user)
        person_id = self.request.query_params.get('person')
        template_id = self.request.query_params.get('template')
        if person_id:
            qs = qs.filter(person_id=person_id)
        if template_id:
            qs = qs.filter(template_id=template_id)
        return qs

    def create(self, request, *args, **kwargs):
        """
        Crea el turno fijo y materializa las reservas (Appointment) sobre los Slots
        existentes del template dentro de [start_date, end_date].
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            fixed_slot = serializer.save()
            reservas_creadas, warnings = fixed_slot.reserve_existing_slots()

            if not fixed_slot.person.has_active_plan():
                warnings.append({"date": None, "slot": None, "reason": "sin_plan_activo"})

            Action.objects.create(
                user=request.user,
                action="Crear",
                target="Turno fijo",
                target_id=fixed_slot.id,
                new_value=[
                    {"field": "Alumno", "value": f"{fixed_slot.person}"},
                    {"field": "Template", "value": f"{fixed_slot.template}"},
                    {"field": "Reservas creadas", "value": str(reservas_creadas)},
                    {"field": "Advertencias", "value": str(len(warnings))},
                ],
            )

        headers = self.get_success_headers(serializer.data)
        data = self.get_serializer(fixed_slot).data
        data['reservas_creadas'] = reservas_creadas
        data['warnings'] = warnings
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)
