from rest_framework import viewsets
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper, StudentReadMixin
from .models import Room
from .serializers import RoomSerializer

class RoomViewSet(StudentReadMixin, viewsets.ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    write_permission = IsAdministrador | IsConsultor | IsSuper

    def get_queryset(self):
        return Room.all_objects.for_user(self.request.user).select_related("studio").order_by("studio__name", "name")
