
from rest_framework import viewsets
from .serializer import StatusSerializer
from .models import Status
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper

class StatusViewSet(viewsets.ModelViewSet):
    queryset = Status.objects.all()
    serializer_class = StatusSerializer
    permission_classes = [IsSuper]

    def get_queryset(self):
        return Status.all_objects.for_user(self.request.user)
