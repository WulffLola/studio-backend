from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .serializer import AppointmentSerializer, CalendarSlotSerializer
from .models import Appointment
from apps.slots.models import Slot
from apps.users.models import CustomUser
from apps.actions.models import Action
from datetime import datetime
from apps.people.models import Person
from apps.waiting_list.models import WaitingList
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper, IsStudent
import logging
import requests
import os
from datetime import datetime, timedelta
from django.db import transaction
from django.utils import timezone
from apps.people.selectors import find_consumable_plan, person_has_plan_for_activity
from apps.teachers_turn.selectors import teachers_turn_prefetch
from apps.studios.filters import StudioFilterMixin

logger = logging.getLogger(__name__)

CANCEL_HOURS_LIMIT = int(os.getenv('CANCEL_HOURS_LIMIT', 2))

# Nombres de día en español, índice 0 = Lunes (igual que date.weekday())
WEEKDAY_NAMES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']


def _slot_day_name(slot):
    """Retorna el nombre del día de la semana en español derivado de slot.date."""
    return WEEKDAY_NAMES[slot.date.weekday()] if slot.date else 'Unknown'


class AppointmentsViewSet(StudioFilterMixin, viewsets.ModelViewSet):
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer
    permission_classes = [IsAdministrador | IsConsultor | IsSuper | IsStudent]
    studio_lookup = 'slot__room__studio'  # appointment -> slot -> room -> studio

    def studio_filter_enabled(self):
        # el filtro por estudio es solo para staff. Los alumnos ya ven
        # únicamente sus reservas y para ellos el parámetro se ignora (como antes).
        return not self.request.user.is_student_user

    def get_queryset(self):
        user = self.request.user
        qs = Appointment.all_objects.for_user(user).select_related(
            'person', 'slot', 'slot__status', 'slot__template',
        )
        # precargar los docentes del slot anidado (evita N+1 en el
        # campo `teachers` de SlotSerializer al serializar cada appointment).
        qs = qs.prefetch_related(
            teachers_turn_prefetch('slot__teachers_turn'),
            'person__sworn_statements__statement',
            'sworn_statements__statement',
        )

        # la vista (list) no muestra turnos eliminados para NINGÚN rol
        # (for_user devuelve también los soft-deleted a admin/super). Las acciones
        # de escritura (destroy/cancel) no son 'list', así que siguen viendo los
        # eliminados para poder detectar "ya eliminado".
        if self.action == 'list':
            qs = qs.filter(deleted__isnull=True)

        # Alumno (puro o con flag): solo ve sus propias reservas
        if user.is_student_user:
            if user.person_id:
                return qs.filter(person_id=user.person_id)
            return qs.none()

        # Staff: filtros opcionales
        date_from = self.request.query_params.get('date_from')
        date_to   = self.request.query_params.get('date_to')
        person_id = self.request.query_params.get('person_id')
        if date_from:
            qs = qs.filter(slot__date__gte=date_from)
        if date_to:
            qs = qs.filter(slot__date__lte=date_to)
        if person_id:
            qs = qs.filter(person_id=person_id)
        # filtro opcional ?studio=<id>[,<id>...] (ver apps/studios/filters.py),
        # combinable con date_from / date_to / person_id.
        return self.filter_by_studio(qs)

    def verify_code(self, code, request):
        """
        Verifica la validez del código y maneja el caso de 'admin' o 'super'.
        """
        if not code:
            return Response({"detail": "El campo 'code' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        # Verificar si el código es "admin" o "super" y usar el usuario logueado
        if code == "admin" or code == "super":
            if request.user.is_authenticated:
                return request.user
            else:
                return Response({"detail": "No hay ningún usuario logueado."}, status=status.HTTP_400_BAD_REQUEST)

        # Buscar el usuario que tenga ese código
        try:
            user = CustomUser.objects.get(code=code)
            return user
        except CustomUser.DoesNotExist:
            return Response({"detail": "El código proporcionado no corresponde a ningún usuario."}, status=status.HTTP_400_BAD_REQUEST)
            
    def _enforce_student_cancel_window(self, request, instance):
        """Si el que cancela es alumno, no puede hacerlo con menos de
        CANCEL_HOURS_LIMIT horas de anticipación. El staff (Admin/Consultor/Super)
        puede cancelar siempre. Devuelve un Response 400 si corresponde bloquear, o
        None. Se aplica en cancel() y destroy() para que no se contradigan."""
        if not getattr(request.user, 'is_student_user', False):
            return None
        slot = instance.slot
        if slot and slot.date and slot.start_time:
            slot_dt = datetime.combine(slot.date, slot.start_time)
            slot_dt = timezone.make_aware(slot_dt) if timezone.is_naive(slot_dt) else slot_dt
            hours_left = (slot_dt - timezone.now()).total_seconds() / 3600
            if hours_left < CANCEL_HOURS_LIMIT:
                return Response(
                    {"detail": f"No se puede cancelar con menos de {CANCEL_HOURS_LIMIT} horas de anticipación."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return None

    def _soft_cancel(self, instance, user, action_label):
        """Lógica común de cancelación de un turno: libera el slot, soft-delete del
        appointment, devuelve la sesión consumida y registra el audit.
        Compartida por destroy() y cancel() para que no se contradigan."""
        slot = instance.slot
        person = instance.person

        slot.availability += 1
        if slot.availability > 0:
            slot.status_id = 1
        slot.save()

        instance.deleted = timezone.now()
        instance.save()

        if instance.consumed_plan_id and instance.consumed_plan and instance.consumed_plan.deleted is None:
            instance.consumed_plan.restore_session()

        Action.objects.create(
            user=user,
            action=action_label,
            target="Turno",
            target_id=instance.id,
            old_value=[
                {'field': 'Turno', 'value': f"{slot.date} a las {slot.start_time.strftime('%H:%M') if slot.start_time else ''}"},
                {'field': 'Persona', 'value': f"{person.name} {person.last_name}"},
            ],
        )

    def _active_plans(self, person):
        """PersonActivePlan activos (no eliminados, no vencidos) de la persona."""
        from apps.people.models import PersonActivePlan
        from django.utils import timezone
        today = timezone.now().date()
        return PersonActivePlan.objects.filter(
            person=person, deleted__isnull=True, exp_date__gte=today,
        )

    def send_waitlist_message(self, appointment, code):
        """
        Sends a waitlist message to the configured external API using appointment details.
        """
        person = appointment.person
        slot = appointment.slot

        if not person or not slot:
            logger.warning("Appointment missing person or slot.")
            return

        if not person.phone:
            logger.warning(f"Person {person.id} has no phone number.")
            return
        
        waiting_list = WaitingList.objects.filter(
            person=person,
            slot=slot,
            deleted__isnull=True
        ).first()

        name = f"{person.name} {person.last_name}".strip()
        phone = person.phone
        day = _slot_day_name(slot)
        hour = slot.start_time.strftime('%H:%M') if slot.start_time else "Unknown"
        limit_hour = (datetime.now() + timedelta(hours=3)).strftime('%H:%M')
        waiting_list_id = waiting_list.id if waiting_list else None


        payload = {
            "phone": phone,
            "name": name,
            "day": day,
            "hour": hour,
            "limitHour": limit_hour,
            "appointment_id": appointment.id,
            "slot_id": slot.id,
            "person_id": person.id,
            "waiting_list_id": waiting_list_id, 
            "code": code
        }

        api_url = os.getenv("API_WPP_SEND_WAITLIST")
        if not api_url:
            logger.error("API_WPP_SEND_WAITLIST environment variable not set.")
            return

        try:
            response = requests.post(api_url, json=payload, timeout=5)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to send waitlist message: {str(e)}")

    def create(self, request, *args, **kwargs):
        # Obtener el código del usuario de la solicitud
        code = request.data.get('code')
        user = self.verify_code(code, request)
        
        # Si el código es inválido, la función verify_code retornará un Response con el error
        if isinstance(user, Response):
            return user

        # Validar el resto de los datos de la solicitud
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # Validar los datos entrantes
        
        # Obtener los objetos de person y slot validados
        slot = serializer.validated_data['slot']
        person = serializer.validated_data['person']
        
        # Verificar si ya existe el Appointment con la misma persona y slot
        if Appointment.objects.filter(slot=slot, person=person, deleted__isnull=True).exists():
            return Response(
                {"detail": "La persona ya está registrada en ese turno."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if slot.status_id == 2:
            return Response(
                {"detail": "El cupo en este horario está lleno."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # resolver el plan a consumir (si el alumno depende de un plan
        # para esta actividad y no le quedan sesiones, no puede reservar).
        plan = find_consumable_plan(person, slot)
        if plan is None and person_has_plan_for_activity(person, slot):
            return Response(
                {"detail": "No te quedan sesiones en tu plan para esta actividad."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # descontar la sesión ANTES de crear el turno, de forma atómica.
            # Si otra reserva concurrente se llevó la última, deduct_session()
            # devuelve False y rechazamos la reserva (nada se crea ni se descuenta).
            if plan is not None and not plan.deduct_session():
                return Response(
                    {"detail": "No te quedan sesiones en tu plan para esta actividad."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Actualizar la disponibilidad del slot
            slot.availability -= 1
            if slot.availability == 0:
                slot.status_id = 2
            slot.save()

            # Crear el appointment utilizando los datos validados
            appointment = serializer.save()

            # trazar el plan consumido en el appointment
            if plan is not None:
                appointment.consumed_plan = plan
                appointment.save(update_fields=['consumed_plan'])

        # Después de guardar el appointment, si la persona no tiene plan activo y
        # exp_date está vacío, asignar fecha de hoy
        if not self._active_plans(person).exists() and not person.exp_date:
            person.exp_date = datetime.now().date()
            person.save()

        # Crear el JSON con el nuevo valor
        new_value = [
            {'field': 'Turno', 'value': f"{slot.date} a las {slot.start_time.strftime('%H:%M') if slot.start_time else 'Unknown'}"},
            {'field': 'Persona', 'value': f"{person.name} {person.last_name}"}
        ]

        # Registrar la acción en el modelo Action
        Action.objects.create(
            user=user,
            action="Crear",
            target="Turno",
            target_id=appointment.id,  # ID del appointment creado
            new_value=new_value,  # Valores nuevos en formato JSON
        )
        if appointment.reserved:
            self.send_waitlist_message(appointment, code)

        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_201_CREATED)
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)  # Manejar actualización parcial si se solicita
        instance = self.get_object()  # Obtener la instancia del Appointment que se va a actualizar

        # Obtener el código del usuario de la solicitud
        code = request.data.get('code')
        user = self.verify_code(code, request)

        if isinstance(user, Response):
            return user  # Si el código es inválido, retornará un error

        # Guardar el valor anterior para el registro de la acción
        old_slot = instance.slot
        old_person = instance.person
        
        # Validar si se está cambiando de persona
        new_person_id = request.data.get('person', None)
        if new_person_id and int(new_person_id) != old_person.id:
            try:
                new_person = Person.objects.get(id=new_person_id)

                # Asignar exp_date si la persona no tiene plan activo y está vacío
                if not self._active_plans(new_person).exists() and not new_person.exp_date:
                    new_person.exp_date = datetime.now().date()
                    new_person.save()
                    
            except Person.DoesNotExist:
                return Response({"detail": "La persona no existe."}, status=status.HTTP_404_NOT_FOUND)

        # Crear el JSON con el valor anterior
        old_value = [
            {'field': 'Turno', 'value': f"{_slot_day_name(old_slot)} a las {old_slot.start_time.strftime('%H:%M') if old_slot.start_time else 'Unknown'}"},
            {'field': 'Persona', 'value': f"{old_person.name} {old_person.last_name}"}
        ]

        # Validar los datos entrantes
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # Obtener los nuevos valores
        new_slot = serializer.validated_data.get('slot', instance.slot)
        new_person = serializer.validated_data.get('person', instance.person)

        # Verificar si la persona ya está registrada en ese nuevo turno
        if Appointment.objects.filter(
                slot=new_slot,
                person=new_person,
                deleted__isnull=True
            ).exclude(id=instance.id).exists():

            return Response(
                {"detail": "La persona ya está registrada en ese turno."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Actualizar la disponibilidad del slot anterior
        if old_slot != new_slot:
            # availability puede ser NULL en el modelo -> guardar contra None.
            old_slot.availability = (old_slot.availability or 0) + 1
            if old_slot.availability > 0:
                old_slot.status_id = 1
            old_slot.save()

            # Actualizar la disponibilidad del nuevo slot
            new_slot.availability = (new_slot.availability or 0) - 1
            if new_slot.availability == 0:
                new_slot.status_id = 2
            new_slot.save()

        # Guardar el appointment actualizado
        appointment = serializer.save()

        # Crear el JSON con el nuevo valor
        new_value = [
            {'field': 'Turno', 'value': f"{_slot_day_name(new_slot)} a las {new_slot.start_time.strftime('%H:%M') if new_slot.start_time else 'Unknown'}"},
            {'field': 'Persona', 'value': f"{new_person.name} {new_person.last_name}"}
        ]

        # Registrar la acción en el modelo Action
        Action.objects.create(
            user=user,
            action="Actualizar",
            target="Turno",
            target_id=appointment.id,
            old_value=old_value,
            new_value=new_value,
        )

        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()  # Obtener el appointment a eliminar

        # Obtener el código del usuario de la solicitud
        code = request.data.get('code')
        user = self.verify_code(code, request)

        if isinstance(user, Response):
            return user  # Si el código es inválido, retornará un error

        # si ya estaba eliminado (p.ej. get_queryset de Super/Admin
        # incluye soft-deleted), cortar acá para no re-devolver sesión ni
        # re-incrementar la disponibilidad del slot.
        if instance.deleted:
            return Response({"detail": "El turno ya fue eliminado."}, status=status.HTTP_404_NOT_FOUND)

        # DELETE no puede saltear la regla de las 2 hs para alumnos.
        err = self._enforce_student_cancel_window(request, instance)
        if err:
            return err

        self._soft_cancel(instance, user, "Eliminar")
        return Response(status=status.HTTP_204_NO_CONTENT)


    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        POST /appointments/{id}/cancel/
        Cancela una reserva. Para alumnos, solo si falta más de CANCEL_HOURS_LIMIT
        horas para el turno (el staff puede cancelar siempre). Acepta 'code' igual
        que destroy. Comparte la lógica con destroy() vía _soft_cancel.
        """
        instance = self.get_object()

        code = request.data.get('code')
        user = self.verify_code(code, request)
        if isinstance(user, Response):
            return user

        # si ya estaba eliminado (p.ej. get_queryset de Super/Admin
        # incluye soft-deleted), cortar acá para no re-devolver sesión ni
        # re-incrementar la disponibilidad del slot.
        if instance.deleted:
            return Response({"detail": "El turno ya fue eliminado."}, status=status.HTTP_404_NOT_FOUND)

        # el límite de 2 hs aplica a alumnos; el staff puede cancelar siempre.
        err = self._enforce_student_cancel_window(request, instance)
        if err:
            return err

        self._soft_cancel(instance, user, "Cancelar")
        return Response(status=status.HTTP_204_NO_CONTENT)


class UpcomingAppointmentsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /upcoming-appointments/
    Reservas con slot.date >= hoy. Param opcional: ?person_id=<id>
    Alumnos (puro o is_student) ven automáticamente solo las suyas.
    """
    serializer_class = AppointmentSerializer
    permission_classes = [IsAdministrador | IsConsultor | IsSuper | IsStudent]

    def get_queryset(self):
        user = self.request.user
        today = timezone.now().date()
        qs = Appointment.objects.filter(
            slot__date__gte=today,
            deleted__isnull=True,
        ).select_related('slot', 'person').prefetch_related(
            teachers_turn_prefetch('slot__teachers_turn')  #
        )

        if user.is_student_user:
            return qs.filter(person_id=user.person_id).order_by('slot__date', 'slot__start_time')

        person_id = self.request.query_params.get('person_id')
        if person_id:
            qs = qs.filter(person_id=person_id)
        return qs.order_by('slot__date', 'slot__start_time')


class PastAppointmentsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /past-appointments/
    Reservas con slot.date < hoy. Param opcional: ?person_id=<id>
    Alumnos (puro o is_student) ven automáticamente solo las suyas.
    """
    serializer_class = AppointmentSerializer
    permission_classes = [IsAdministrador | IsConsultor | IsSuper | IsStudent]

    def get_queryset(self):
        user = self.request.user
        today = timezone.now().date()
        qs = Appointment.objects.filter(
            slot__date__lt=today,
            deleted__isnull=True,
        ).select_related('slot', 'person').prefetch_related(
            teachers_turn_prefetch('slot__teachers_turn')  #
        )

        if user.is_student_user:
            return qs.filter(person_id=user.person_id).order_by('-slot__date', 'slot__start_time')

        person_id = self.request.query_params.get('person_id')
        if person_id:
            qs = qs.filter(person_id=person_id)
        return qs.order_by('-slot__date', 'slot__start_time')


class AppointmentsByDayViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AppointmentSerializer
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]
    def get_queryset(self):
        day_of_week = self.kwargs.get('day_of_week')
        
        try:
            day_of_week = int(day_of_week)
            if day_of_week < 1 or day_of_week > 7:
                raise ValueError
        except (ValueError, TypeError):
            return Appointment.objects.none() 

        return Appointment.objects.filter(slot__date__iso_week_day=day_of_week, deleted__isnull=True)


class EnrollmentCheckView(viewsets.ViewSet):
    """
    GET /enrollment-check/?person=<id>&slot=<id>

    Verifica si una persona tiene un plan activo que cubre la actividad del slot.
    - covered: true  -> active_plan con sesiones y vencimiento
    - covered: false -> required_plans_type que debe comprar
    """
    permission_classes = [IsAdministrador | IsConsultor | IsSuper | IsStudent]

    def list(self, request, *args, **kwargs):
        from django.utils import timezone
        from apps.people.models import PersonActivePlan
        from apps.people.serializer import PersonActivePlanSerializer
        from apps.plans_subtype.serializer import PlansSubtypeSerializer

        person_id = request.query_params.get('person')
        slot_id = request.query_params.get('slot')

        if not person_id or not slot_id:
            return Response(
                {"detail": "Se requieren los parámetros 'person' y 'slot'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            slot = Slot.objects.get(pk=slot_id)
        except Slot.DoesNotExist:
            return Response({"detail": "Slot no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if not slot.activity_subtype:
            return Response(
                {"detail": "El slot no tiene actividad asignada."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.now().date()

        # Buscar plan activo del alumno cuyo subtype cubre la actividad del slot
        active_plan = PersonActivePlan.objects.filter(
            person_id=person_id,
            plans_subtype__activity_subtype=slot.activity_subtype,
            exp_date__gte=today,
            sessions_remaining__gt=0,
            deleted__isnull=True,
        ).first()

        if active_plan:
            return Response({
                "covered": True,
                "active_plan": PersonActivePlanSerializer(active_plan).data,
            })

        # Devolver los subtypes disponibles para esa actividad como referencia
        from django.db.models import Prefetch
        from apps.plans_subtype.models import PlansSubtype
        from apps.payment_method.models import PaymentMethod
        available_subtypes = PlansSubtype.objects.filter(
            activity_subtype=slot.activity_subtype,
            deleted__isnull=True,
        ).prefetch_related(
            Prefetch(
                'payment_methods',
                queryset=PaymentMethod.objects.filter(deleted__isnull=True),
                to_attr='alive_payment_methods',
            )
        )
        return Response({
            "covered": False,
            "required_plans_subtypes": PlansSubtypeSerializer(available_subtypes, many=True).data,
        })


class CalendarViewSet(viewsets.ViewSet):
    """
    GET /calendar/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD

    Devuelve los slots del rango agrupados por fecha, cada uno con sus reservas activas.

    Respuesta:
    [
      {
        "date": "2026-03-21",
        "slots": [
          {
            "id": 1,
            "start_time": "09:00", "end_time": "10:00",
            "week_day_name": "Lunes",
            "room_name": "Sala A", "studio_name": "Estudio Central",
            "activity": "Yoga",
            "availability": 3, "capacity": 10,
            "status_name": "disponible",
            "appointments": [
              {"id": 1, "person_id": 5, "person_name": "Ana Lopez", "person_photo": null, "reserved": false}
            ]
          }
        ]
      }
    ]

    Parámetros opcionales:
      - date_from  (default: hoy)
      - date_to    (default: hoy + 6 días)
    """
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]

    def list(self, request, *args, **kwargs):
        from datetime import date, timedelta
        from collections import defaultdict

        raw_from = request.query_params.get('date_from')
        raw_to   = request.query_params.get('date_to')

        if not raw_from or not raw_to:
            return Response(
                {"detail": "Los parámetros date_from y date_to son requeridos (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            date_from = datetime.strptime(raw_from, '%Y-%m-%d').date()
            date_to   = datetime.strptime(raw_to,   '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {"detail": "Formato de fecha inválido. Usar YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if date_from > date_to:
            return Response(
                {"detail": "date_from no puede ser posterior a date_to."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        slots = (
            Slot.objects.filter(
                date__gte=date_from,
                date__lte=date_to,
                deleted__isnull=True,
            )
            .select_related('status', 'room', 'room__studio', 'activity_subtype')
            .prefetch_related(
                'appointments__person',
            )
            .order_by('date', 'start_time')
        )

        grouped = defaultdict(list)
        for slot in slots:
            grouped[slot.date].append(slot)

        result = []
        current = date_from
        while current <= date_to:
            day_slots = grouped.get(current, [])
            result.append({
                "date": current.isoformat(),
                "slots": CalendarSlotSerializer(
                    day_slots, many=True, context={'request': request}
                ).data,
            })
            current += timedelta(days=1)

        return Response(result)