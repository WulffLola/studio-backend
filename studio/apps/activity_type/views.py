from rest_framework import viewsets
from .serializer import ActivityTypeSerializer
from .models import ActivityType
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper, StudentReadMixin

class ActivityTypeViewSet(StudentReadMixin, viewsets.ModelViewSet):
    queryset = ActivityType.objects.all()
    serializer_class = ActivityTypeSerializer
    write_permission = IsAdministrador | IsConsultor | IsSuper

    def get_queryset(self):
        return ActivityType.all_objects.for_user(self.request.user)
