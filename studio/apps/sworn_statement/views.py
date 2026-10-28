from rest_framework import viewsets, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from apps.user_type.permisos import IsAdministrador, IsSuper, IsStudent
from .models import SwornStatement, PersonSwornStatement, AppointmentSwornStatement
from .serializer import (
    SwornStatementSerializer,
    PersonSwornStatementSerializer,
    PersonSwornStatementReadSerializer,
    AppointmentSwornStatementSerializer,
    AppointmentSwornStatementReadSerializer,
)

User = get_user_model()


class SwornStatementViewSet(viewsets.ModelViewSet):
    """
    GET  /sworn-statement/       -> texto activo de la declaración (público, para mostrar en registro)
    POST /sworn-statement/       -> crea una nueva versión del texto (admin)
    PATCH/PUT /sworn-statement/{id}/ -> edita el texto (admin)
    DELETE /sworn-statement/{id}/    -> soft delete (admin)
    """
    serializer_class = SwornStatementSerializer

    def get_queryset(self):
        return SwornStatement.objects.all()

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return [(IsAdministrador | IsSuper)()]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PersonSwornStatementViewSet(viewsets.ModelViewSet):
    """
    GET  /person-sworn-statement/       -> listado de firmas (admin)
    POST /person-sworn-statement/       -> registrar firma

    Body POST:
        user_id:   <id del CustomUser>  (se resuelve a su Person asociada)
        statement: <id del SwornStatement>
    """
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = PersonSwornStatement.objects.select_related('person', 'statement').all()
        is_admin = (
            IsAdministrador().has_permission(self.request, self)
            or IsSuper().has_permission(self.request, self)
        )
        if not is_admin:
            person = getattr(self.request.user, 'person', None)
            qs = qs.filter(person=person) if person is not None else qs.none()
        return qs

    def get_serializer_class(self):
        if self.action in ('list', 'retrieve'):
            return PersonSwornStatementReadSerializer
        return PersonSwornStatementSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated()]
        return [(IsAdministrador | IsSuper | IsStudent)()]

    def create(self, request, *args, **kwargs):
        statement_id = request.data.get('statement')
        if not statement_id:
            return Response({'detail': 'statement es requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        # Admin/Super pueden firmar por otro (pasando user_id); el resto solo por sí mismo.
        is_admin = (
            IsAdministrador().has_permission(request, self)
            or IsSuper().has_permission(request, self)
        )
        if is_admin:
            user_id = request.data.get('user_id') or request.user.id
        else:
            user_id = request.user.id

        try:
            user = User.objects.select_related('person').get(pk=user_id)
        except User.DoesNotExist:
            return Response({'detail': 'Usuario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        if not user.person:
            return Response({'detail': 'El usuario no tiene un perfil de persona asociado.'}, status=status.HTTP_400_BAD_REQUEST)

        data = {'person': user.person.id, 'statement': statement_id}
        serializer = PersonSwornStatementSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AppointmentSwornStatementViewSet(viewsets.ModelViewSet):
    """
    GET  /appointment-sworn-statement/?appointment=<id>  -> firmas de un appointment
    POST /appointment-sworn-statement/                   -> registrar firma para un appointment
    DELETE /appointment-sworn-statement/{id}/            -> eliminar (admin)

    Body POST:
        appointment: <id>   (para no-admin, debe ser un turno propio)
        statement: <id>
    """
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = AppointmentSwornStatement.objects.select_related('appointment', 'statement').all()
        is_admin = (
            IsAdministrador().has_permission(self.request, self)
            or IsSuper().has_permission(self.request, self)
        )
        if not is_admin:
            person = getattr(self.request.user, 'person', None)
            qs = qs.filter(appointment__person=person) if person is not None else qs.none()
        appointment_id = self.request.query_params.get('appointment')
        if appointment_id:
            qs = qs.filter(appointment_id=appointment_id)
        return qs

    def get_serializer_class(self):
        if self.action in ('list', 'retrieve'):
            return AppointmentSwornStatementReadSerializer
        return AppointmentSwornStatementSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated()]
        if self.action == 'destroy':
            return [(IsAdministrador | IsSuper)()]
        return [(IsAdministrador | IsSuper | IsStudent)()]

    def create(self, request, *args, **kwargs):
        appointment_id = request.data.get('appointment')
        statement_id = request.data.get('statement')
        if not appointment_id:
            return Response({'detail': 'appointment es requerido.'}, status=status.HTTP_400_BAD_REQUEST)
        if not statement_id:
            return Response({'detail': 'statement es requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.appointments.models import Appointment
        try:
            appointment = Appointment.objects.select_related('person').get(pk=appointment_id)
        except Appointment.DoesNotExist:
            return Response({'detail': 'Turno no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        # Admin/Super pueden firmar por cualquier turno; el resto solo sobre turnos propios.
        is_admin = (
            IsAdministrador().has_permission(request, self)
            or IsSuper().has_permission(request, self)
        )
        if not is_admin:
            user_person = getattr(request.user, 'person', None)
            if user_person is None or appointment.person_id != user_person.id:
                return Response(
                    {'detail': 'No podés firmar la declaración de un turno que no te pertenece.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        data = {'appointment': appointment.id, 'statement': statement_id}
        serializer = AppointmentSwornStatementSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
