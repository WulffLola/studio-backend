
from apps.teachers.models import Teacher
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import ExtraHours
from .serializer import ExtraHoursSerializer
from apps.teachers_hours.models import Hour
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper
from django.utils.timezone import now

class ExtraHoursViewSet(viewsets.ModelViewSet):
    queryset = ExtraHours.objects.all()
    serializer_class = ExtraHoursSerializer
    permission_classes = [IsAdministrador | IsSuper]

    def get_queryset(self):
        return ExtraHours.all_objects.for_user(self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        extra_hour_data = serializer.validated_data
        teacher = extra_hour_data.get('teacher')
        slot = extra_hour_data.get('slot')
        date = slot.date if slot else None

        if not date:
            return Response(
                {"detail": "El slot seleccionado no tiene fecha asignada."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Conflicto POR DÍA + horario: mismo profesor, mismo día (slot__date) y
        # misma hora (slot__start_time). Se valida cada día de forma independiente,
        # así las horas de otro día no interfieren.
        if ExtraHours.objects.filter(
            teacher=teacher, slot__date=slot.date, slot__start_time=slot.start_time,
            deleted__isnull=True,
        ).exists():
            hora = slot.start_time.strftime('%H:%M') if slot.start_time else '—'
            return Response(
                {"detail": f"Ya existe una hora extra para esta profesora el {slot.date} a las {hora}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        month = date.strftime('%m')
        hour_instance = get_object_or_404(Hour, teacher=teacher, month=month, deleted__isnull=True)

        hour_instance.extra_hour = str(int(hour_instance.extra_hour or 0) + 1)

        price = extra_hour_data.get('price', 0)
        hour_instance.total = str(float(hour_instance.total or 0) + price)
        hour_instance.left = str(float(hour_instance.left or 0) + price)
        hour_instance.save()

        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        teacher = serializer.validated_data.get('teacher', instance.teacher)
        slot = serializer.validated_data.get('slot', instance.slot)

        # Conflicto POR DÍA + horario (excluyendo la propia fila).
        if ExtraHours.objects.filter(
            teacher=teacher, slot__date=slot.date, slot__start_time=slot.start_time,
            deleted__isnull=True,
        ).exclude(pk=instance.pk).exists():
            hora = slot.start_time.strftime('%H:%M') if slot.start_time else '—'
            return Response(
                {"detail": f"Ya existe una hora extra para esta profesora el {slot.date} a las {hora}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        teacher = instance.teacher
        date = instance.slot.date if instance.slot else None
        price = instance.price

        if date:
            month = date.strftime('%m')
            hour_instance = Hour.objects.filter(teacher=teacher, month=month, deleted__isnull=True).first()
            if hour_instance:
                extra_hours = int(hour_instance.extra_hour or 0)
                if extra_hours > 0:
                    hour_instance.extra_hour = str(extra_hours - 1)
                left_value = float(hour_instance.left or 0)
                hour_instance.left = str(max(left_value - price, 0))
                hour_instance.save()

        instance.deleted = now()
        instance.save()

        return Response(status=status.HTTP_204_NO_CONTENT)


class TeacherExtraHoursViewSet(viewsets.ViewSet):

    permission_classes = [IsAdministrador | IsSuper]

    def list(self, request, *args, **kwargs):
        teacher_id = kwargs.get('teacher_id')

        if not teacher_id:
            return Response({"detail": "Falta el parámetro teacher_id."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            teacher = Teacher.objects.get(pk=teacher_id)
        except Teacher.DoesNotExist:
            return Response({"detail": "Profesor no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        last_payment_date = teacher.last_payment
        if not last_payment_date:
            return Response({"detail": "No se encontró la fecha de last_payment para este profesor."}, status=status.HTTP_404_NOT_FOUND)

        # Filtrar por slot__date ya que el modelo no tiene campo date propio
        extra_hours = ExtraHours.objects.filter(
            teacher=teacher,
            slot__date__gt=last_payment_date,
            deleted__isnull=True
        )

        serializer = ExtraHoursSerializer(extra_hours, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
