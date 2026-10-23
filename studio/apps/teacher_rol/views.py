
from rest_framework import viewsets
from .serializer import RolSerializer
from .models import Rol
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper

class RolViewSet(viewsets.ModelViewSet):
    serializer_class = RolSerializer
    permission_classes = [IsAdministrador | IsConsultor | IsSuper
]

    def get_queryset(self):
        return Rol.all_objects.for_user(self.request.user)
