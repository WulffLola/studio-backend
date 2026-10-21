
from rest_framework import viewsets
from .serializer import WeekSerializer
from .models import Week
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper

class WeekViewSet(viewsets.ModelViewSet):
    serializer_class = WeekSerializer
    permission_classes = [IsAdministrador | IsConsultor | IsSuper
]

    def get_queryset(self):
        return Week.all_objects.for_user(self.request.user)
