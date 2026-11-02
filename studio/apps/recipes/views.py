from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from apps.user_type.permisos import IsSuper, IsAdministrador, IsConsultor, IsStudent
from .models import Recipe
from .serializers import RecipeSerializer
from .filters import RecipeFilter

class RecipeViewSet(viewsets.ModelViewSet):
    queryset = Recipe.objects.all()
    serializer_class = RecipeSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = RecipeFilter

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        permission_classes = [IsAuthenticated]

        if self.action in ['list', 'retrieve']:
            # Leer: Super, Admin, Consultor, Student
            permission_classes.append(IsSuper | IsAdministrador | IsConsultor | IsStudent)
        else:
            # Crear, Editar, Eliminar: Solo Super o Admin
            permission_classes.append(IsSuper | IsAdministrador)

        return [permission() for permission in permission_classes]
