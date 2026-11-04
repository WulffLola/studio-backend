from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from apps.user_type.permisos import IsAdministrador, IsSuper, StudentReadMixin
from .models import HomePhrase
from .serializer import HomePhraseSerializer


class HomePhraseViewSet(StudentReadMixin, viewsets.ModelViewSet):
    """    GET  /home-phrase/          -> devuelve la frase (la crea vacía si no existe)
    PATCH/PUT /home-phrase/{id}/ -> edita el texto
    """

    queryset = HomePhrase.objects.all()
    serializer_class = HomePhraseSerializer
    write_permission = IsAdministrador | IsSuper

    def get_permissions(self):
        # La frase del inicio es pública: la ven todos los roles (y la app de alumnos).
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return super().get_permissions()
