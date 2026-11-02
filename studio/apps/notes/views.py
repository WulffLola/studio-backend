from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from apps.user_type.permisos import IsSuper, IsAdministrador, IsConsultor, IsStudent
from .models import Note
from .serializers import NoteSerializer
from .filters import NoteFilter

class NoteViewSet(viewsets.ModelViewSet):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = NoteFilter

    def update(self, request, *args, **kwargs):
        if request.data.get('imagen') == 'null':
            request.data['video'] = None
        if request.data.get('video') == 'null':
            request.data['imagen'] = None            
        return super().update(request, *args, **kwargs)
    
    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        # Todos deben estar autenticados
        permission_classes = [IsAuthenticated]

        if self.action in ['list', 'retrieve']:
            # Leer: Super, Admin, Consultor, Student
            permission_classes.append(IsSuper | IsAdministrador | IsConsultor | IsStudent)
        else:
            # Crear, Editar, Eliminar: Solo Super o Admin
            permission_classes.append(IsSuper | IsAdministrador)

        return [permission() for permission in permission_classes]
