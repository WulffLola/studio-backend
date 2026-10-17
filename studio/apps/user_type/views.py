from rest_framework import viewsets
from .serializer import UserTypeSerializer
from .models import UserType
from apps.user_type.permisos import IsSuper, IsAdministrador


class UserTypeViewSet(viewsets.ModelViewSet):
    queryset = UserType.objects.filter()
    serializer_class = UserTypeSerializer
    permission_classes = [IsSuper | IsAdministrador]
