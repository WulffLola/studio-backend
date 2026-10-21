from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from rest_framework.views import APIView
from .serializer import PersonSerializer, PersonWithPlansSerializer, PersonActivePlanSerializer, PersonPhotoSerializer
from .models import Person, PersonActivePlan
from apps.payments.models import Payment
from apps.appointments.models import Appointment
from apps.actions.models import Action  
from apps.users.models import CustomUser 
from datetime import datetime
from django.db.models import Prefetch
from apps.payment_method.models import PaymentMethod
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper

class PeopleViewSet(viewsets.ModelViewSet):
    queryset = Person.objects.all()
    serializer_class = PersonWithPlansSerializer
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]

    def get_queryset(self):
        return Person.all_objects.for_user(self.request.user).prefetch_related(
            Prefetch(
                'active_plans__plans_subtype__payment_methods',
                queryset=PaymentMethod.objects.filter(deleted__isnull=True),
                to_attr='alive_payment_methods',
            )
        )

    def verify_code(self, code, request):
        """
        Verifica la validez del código y maneja el caso de 'admin' o 'super'.
        """
        if not code:
            return Response({"detail": "El campo 'code' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        # Verificar si el código es "admin" o "super" y usar el usuario logueado
        if code == "admin":
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

    def create(self, request, *args, **kwargs):
        data = request.data.copy()

        # Validar los campos obligatorios
        required_fields = ['name', 'last_name', 'dni', 'email', 'phone', 'sex', 'birth_date']
        missing_fields = [field for field in required_fields if not data.get(field)]

        if missing_fields:
            return Response(
                {"error": f"Los siguientes campos son obligatorios y no pueden estar vacíos: {', '.join(missing_fields)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        dni = data.get('dni')
        # Verificar si ya existe una persona con ese DNI
        if Person.objects.filter(dni=dni).exists():
            raise ValidationError({"error": "La persona con este DNI ya está registrada"})

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    def update(self, request, *args, **kwargs):
        person = self.get_object()
        data = request.data.copy()

        # Verificar campos obligatorios
        required_fields = ['name', 'last_name', 'dni', 'email', 'phone', 'sex', 'birth_date']
        missing_fields = [field for field in required_fields if data.get(field) and not data.get(field)]

        if missing_fields:
            return Response(
                {"error": f"Los siguientes campos son obligatorios y no pueden estar vacíos: {', '.join(missing_fields)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        dni = data.get('dni')
        # Verificar si ya existe una persona con ese DNI, excluyendo la actual
        if dni and Person.objects.filter(dni=dni).exclude(id=person.id).exists():
            return Response(
                {"error": "La persona con este DNI ya está registrada"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Manejar el campo 'last_payment' como una fecha
        last_payment = data.get('last_payment')
        if last_payment:
            try:
                # Convertir 'last_payment' a objeto de fecha
                last_payment_date = datetime.strptime(last_payment, '%Y-%m-%d').date()
                data['last_payment'] = last_payment_date  # Asignar la fecha convertida
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha 'last_payment' es incorrecto. Use el formato YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        serializer = self.get_serializer(person, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_200_OK, headers=headers)

    @action(detail=True, methods=['patch'], url_path='upload-photo')
    def upload_photo(self, request, pk=None):
        person = self.get_object()
        serializer = PersonPhotoSerializer(person, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'profile_photo': request.build_absolute_uri(person.profile_photo.url)}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        person = self.get_object()

        # Obtener el código del usuario de la solicitud
        code = request.data.get('code')
        user = self.verify_code(code, request)
        if isinstance(user, Response):
            return user  # Si el código es inválido, retornará un error

        # Marcar las citas de la persona como eliminadas y actualizar la disponibilidad de los slots
        appointments = Appointment.objects.filter(person=person, deleted__isnull=True)
        for appointment in appointments:
            slot = appointment.slot
            slot.availability += 1
            if slot.status_id == 2:
                slot.status_id = 1  # Cambiar el estado del slot si ya no está lleno
            slot.save()
            appointment.deleted = timezone.now()
            appointment.save()

        # Registrar la acción de eliminación con los datos de la persona antes de eliminarla
        old_value = [
            {'field': 'Nombre', 'value': person.name},
            {'field': 'Apellido', 'value': person.last_name},
            {'field': 'Dni', 'value': person.dni},
            {'field': 'Email', 'value': person.email},
            {'field': 'Teléfono', 'value': person.phone}
        ]

        # Cambiar el new_value a un array de JSON
        new_value = [{"field": "Estado", "value": "Eliminado"}]

        Action.objects.create(
            user=user,  # Usuario que realizó la acción
            action="Eliminado",
            target="Persona",
            target_id=person.id,
            old_value=old_value,
            new_value=new_value  # Cambiado a un array de JSON
        )

        # Marcar a la persona como eliminada (soft delete)
        person.exp_date = None
        person.deleted = timezone.now()
        person.save()

        return Response(status=status.HTTP_204_NO_CONTENT)
    
class DeletedPeopleViewSet(viewsets.ModelViewSet):
    serializer_class = PersonSerializer
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]

    def list(self, request):
        # Filtro por fecha de baja (deleted). date_from y date_to son obligatorios,
        # en formato YYYY-MM-DD, y se valida el rango.
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        if not date_from or not date_to:
            return Response(
                {"detail": "Los parámetros 'date_from' y 'date_to' son obligatorios (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {"detail": "Formato de fecha inválido. Utilizá YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if date_from > date_to:
            return Response(
                {"detail": "'date_from' debe ser anterior o igual a 'date_to'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Tope de ancho de rango: evita consultas enormes (una query de turnos por
        # persona dada de baja) al pedir años de historial.
        MAX_RANGE_DAYS = 366
        if (date_to - date_from).days > MAX_RANGE_DAYS:
            return Response(
                {"detail": f"El rango no puede superar {MAX_RANGE_DAYS} días."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deleted_people = Person.all_objects.filter(
            deleted__isnull=False,
            deleted__date__gte=date_from,
            deleted__date__lte=date_to,
        ).order_by('deleted')

        result = {}

        for person in deleted_people:
            # Agrupar por la fecha de baja en hora LOCAL. deleted se guarda en UTC
            # (USE_TZ=True); .date() daría la fecha UTC y una baja de la noche local
            # caería bajo el día siguiente, inconsistente con el filtro __date (que ya
            # usa tz local).
            day = timezone.localtime(person.deleted).date().isoformat()

            if day not in result:
                result[day] = []

            # Solo los últimos turnos: los que estaban vigentes antes de la baja,
            # ordenados por fecha descendente, máximo los últimos 10.
            appointments = (
                Appointment.all_objects
                .filter(person=person, slot__date__lte=person.deleted.date())
                .select_related('slot')
                .order_by('-slot__date', '-slot__start_time')[:10]
            )
            appointments_data = [
                {
                    'id': appt.id,
                    'slot': appt.slot.id if appt.slot else None,
                    'date': appt.slot.date.isoformat() if appt.slot and appt.slot.date else None,
                }
                for appt in appointments
            ]

            result[day].append({
                'id': person.id,
                'name': person.name,
                'last_name': person.last_name,
                'dni': person.dni,
                'appointments': appointments_data,
            })

        return Response(result)


class PersonActivePlanViewSet(viewsets.ModelViewSet):
    serializer_class = PersonActivePlanSerializer
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]

    def get_queryset(self):
        qs = PersonActivePlan.all_objects.for_user(self.request.user).prefetch_related(
            Prefetch(
                'plans_subtype__payment_methods',
                queryset=PaymentMethod.objects.filter(deleted__isnull=True),
                to_attr='alive_payment_methods',
            )
        )
        person_id = self.request.query_params.get('person')
        if person_id:
            qs = qs.filter(person_id=person_id)
        return qs


class PersonLastPlanViewSet(viewsets.ViewSet):
    """
    GET /person-last-plan/?person=<id>

    Devuelve el último plan registrado del alumno (por id desc) y si está activo.

    Respuesta:
    {
        "plan": { ...PersonActivePlan fields... },
        "is_active": true | false,
        "reason": null | "vencido" | "sin_sesiones"
    }

    Si no tiene ningún plan:
    { "plan": null, "is_active": false, "reason": "sin_plan" }
    """
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]

    def list(self, request, *args, **kwargs):
        person_id = request.query_params.get('person')
        if not person_id:
            return Response(
                {"detail": "Se requiere el parámetro 'person'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        last_plan = (
            PersonActivePlan.all_objects
            .filter(person_id=person_id)
            .order_by('-id')
            .first()
        )

        if last_plan is None:
            return Response({"plan": None, "is_active": False, "reason": "sin_plan"})

        today = timezone.now().date()
        is_active = last_plan.deleted is None and last_plan.exp_date >= today and last_plan.sessions_remaining > 0

        if last_plan.deleted is not None or last_plan.exp_date < today:
            reason = "vencido"
        elif last_plan.sessions_remaining <= 0:
            reason = "sin_sesiones"
        else:
            reason = None

        return Response({
            "plan": PersonActivePlanSerializer(last_plan).data,
            "is_active": is_active,
            "reason": reason,
        })