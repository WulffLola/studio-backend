
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from .serializer import TeacherSerializer
from .models import Teacher
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper, StudentReadMixin
from apps.teachers_turn.models import TeachersTurn
from django.utils.timezone import now

class TeachersViewSet(StudentReadMixin, viewsets.ModelViewSet):

    write_permission = IsAdministrador | IsSuper | IsConsultor
    
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer

    def get_queryset(self):
        return Teacher.all_objects.for_user(self.request.user)

    def create(self, request, *args, **kwargs):
        # Verificar si ya existe un profesor con el mismo DNI
        dni = request.data.get('dni')
        if Teacher.objects.filter(dni=dni).exists():
            return Response(
                {'error': 'Ya existe un profesor con ese DNI.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Si no existe, proceder a la creación
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Validar los datos antes de actualizar
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """
        Soft delete del profesor y sus registros relacionados en TeachersTurn y Hour.
        """
        instance = self.get_object()

        # Soft delete del profesor
        instance.delete()

        # Soft delete de los turnos relacionados (TeachersTurn)
        teachers_turns = TeachersTurn.objects.filter(teacher=instance, deleted__isnull=True)
        for turn in teachers_turns:
            turn.deleted = now()
            turn.save()


        return Response(status=status.HTTP_204_NO_CONTENT)