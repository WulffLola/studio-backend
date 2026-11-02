from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from apps.user_type.permisos import IsSuper, IsAdministrador
from .models import Post
from .serializers import PostSerializer
from .filters import PostFilter


class PostViewSet(viewsets.ModelViewSet):
    """CRUD de publicaciones (/posts/).

    `caption` es OPCIONAL al crear/editar: se puede omitir, enviar "" o null
    (null se normaliza a ""). `title` es el único campo requerido.
    """
    queryset = Post.objects.all()
    serializer_class = PostSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = PostFilter

    def get_queryset(self):
        return Post.all_objects.for_user(self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAuthenticated(), (IsSuper | IsAdministrador)()]
