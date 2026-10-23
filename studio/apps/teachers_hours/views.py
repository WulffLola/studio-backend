from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from .serializer import HourSerializer
from .models import Hour
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper

class HourViewSet(viewsets.ModelViewSet):
    serializer_class = HourSerializer
    permission_classes = [IsAdministrador | IsSuper]

    def get_queryset(self):
        return Hour.all_objects.for_user(self.request.user)

    def create(self, request, *args, **kwargs):
        # Crear una copia mutable de los datos de la solicitud
        data = request.data.copy()

        # Validar que no exista un registro con el mismo teacher y month
        teacher = data.get('teacher_id')
        month = data.get('month')

        if Hour.objects.filter(teacher_id=teacher, month=month, deleted__isnull=True).exists():
            raise ValidationError("Ya existe un registro para este mes y profesor.")

        # Establecer valores por defecto para extra_hour y left
        data['extra_hour'] = '0'
        data['left'] = data.get('total', '0')  # Si total no está en los datos, usar '0'

        # Crear el registro
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)
