from rest_framework import viewsets, status
from rest_framework.response import Response
from .serializer import WaitingListSerializer
from .models import WaitingList
from apps.slots.models import Slot
from apps.users.models import CustomUser
from apps.appointments.models import Appointment  
from datetime import datetime
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper
import os
import requests
from datetime import datetime, timedelta



class WaitingListViewSet(viewsets.ModelViewSet):
    queryset = WaitingList.objects.all()
    serializer_class = WaitingListSerializer
    permission_classes = [IsAdministrador | IsSuper | IsConsultor]

    def get_queryset(self):
        return WaitingList.all_objects.for_user(self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        slot = serializer.validated_data['slot']
        person = serializer.validated_data['person']

        # Verificar si la persona ya está en la lista de espera para el mismo slot
        if WaitingList.objects.filter(slot=slot, person=person, deleted__isnull=True).exists():
            return Response(
                {"detail": "La persona ya está registrada en esta lista de espera."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar si la persona ya tiene un appointment en el mismo slot
        if Appointment.objects.filter(slot=slot, person=person, deleted__isnull=True).exists():
            return Response(
                {"detail": "La persona ya tiene un turno en este dia y horario y no puede ser agregada a la lista de espera."},
                status=status.HTTP_400_BAD_REQUEST
            )

        waiting_list = serializer.save()
        return Response(WaitingListSerializer(waiting_list).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        # Obtener la instancia de la lista de espera que se va a actualizar
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Validar los datos enviados
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # Obtener los campos relevantes del request
        slot = serializer.validated_data.get('slot', instance.slot)
        person = serializer.validated_data.get('person', instance.person)

        # Verificar si ya existe otra entrada en la lista de espera para la misma persona y slot
        if WaitingList.objects.filter(slot=slot, person=person, deleted__isnull=True).exclude(id=instance.id).exists():
            return Response(
                {"detail": "Ya existe una entrada en la lista de espera para esta persona en este slot."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar si la persona ya tiene un appointment en el mismo slot
        if Appointment.objects.filter(slot=slot, person=person, deleted__isnull=True).exists():
            return Response(
                {"detail": "La persona ya tiene un turno en este dia y horario y no puede ser agregada a la lista de espera."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Actualizar la instancia
        self.perform_update(serializer)
        return Response(serializer.data)

