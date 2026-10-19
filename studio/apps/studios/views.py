from rest_framework import viewsets
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper, StudentReadMixin
from .models import Studio
from .serializers import StudioSerializer

class StudioViewSet(StudentReadMixin, viewsets.ModelViewSet):
    queryset = Studio.objects.all()
    serializer_class = StudioSerializer
    write_permission = IsAdministrador | IsConsultor | IsSuper

    def get_queryset(self):
        return Studio.all_objects.for_user(self.request.user).order_by("name")
