
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework import generics
from .serializer import TeachersTurnSerializer
from .models import TeachersTurn
from apps.slots.models import Slot
from apps.users.models import CustomUser  # Importar el modelo de usuario
from apps.actions.models import Action
from datetime import datetime
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper
from apps.studios.filters import StudioFilterMixin
from .selectors import teachers_turn_prefetch


class TeachersTurnViewSet(StudioFilterMixin, viewsets.ModelViewSet):
    queryset = TeachersTurn.objects.all()
    serializer_class = TeachersTurnSerializer
    permission_classes = [IsAdministrador | IsSuper]
    studio_lookup = 'slot__room__studio'  # teachers_turn -> slot -> room -> studio

    def get_queryset(self):
        qs = (
            TeachersTurn.all_objects.for_user(self.request.user)
            .select_related('teacher', 'slot', 'slot__status', 'slot__template')
            .prefetch_related(teachers_turn_prefetch('slot__teachers_turn'))
        )
        # filtro opcional ?studio=<id>[,<id>...] (ver apps/studios/filters.py)
        return self.filter_by_studio(qs)

    def is_teacher_in_slot_with_conflict(self, teacher, slot, rol):
        """
        Verifica si el profesor ya está asignado al slot con el mismo rol (insensible a mayúsculas/minúsculas).
        """
        # Revisa si ya existe un registro con el mismo profesor, slot y rol (insensible a mayúsculas/minúsculas)
        existing_turn = TeachersTurn.objects.filter(
            teacher=teacher, 
            slot=slot, 
            deleted__isnull=True
        ).first()

        if existing_turn:
            # Si ya existe, verifica si el rol es el mismo (insensible a mayúsculas/minúsculas)
            return existing_turn.rol.lower() == rol.lower()

        return False  # No hay conflicto si no hay registros existentes


    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Obtener datos validados del serializer
        teacher = serializer.validated_data['teacher']
        slot = serializer.validated_data['slot']
        #is_receptionist = serializer.validated_data['is_receptionist']
        rol = serializer.validated_data['rol']


        # Verificar conflicto
        if self.is_teacher_in_slot_with_conflict(teacher, slot, rol):
            return Response(
                {"detail": f"La profesora {teacher.name} {teacher.last_name} ya está asignada al slot con otro rol."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Incrementar el campo `hours` del teacher
        teacher.hours = int(teacher.hours or 0) + 1  # Asegurarse de que `hours` sea un número
        teacher.save()

        # Crear el turno del maestro
        self.perform_create(serializer)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # Verificar si el mismo profesor ya está en el slot con un rol diferente
        teacher = serializer.validated_data.get('teacher', instance.teacher)
        slot = serializer.validated_data.get('slot', instance.slot)
        #is_receptionist = serializer.validated_data.get('is_receptionist', instance.is_receptionist)
        rol = serializer.validated_data.get('rol', instance.rol)


        if self.is_teacher_in_slot_with_conflict(teacher, slot, rol):
            return Response(
                {"detail": f"La profesora {teacher.name} {teacher.last_name} ya está asignada al slot con otro rol."},
                status=status.HTTP_400_BAD_REQUEST
            )

        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        # Decrementar el campo `hours` del teacher en 1 antes de eliminar el turno
        teacher = instance.teacher
        teacher.hours = int(teacher.hours or 0) - 1
        teacher.save()

        # Soft delete: actualiza el campo `deleted`
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

