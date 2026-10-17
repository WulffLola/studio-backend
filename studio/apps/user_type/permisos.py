from rest_framework import permissions
from .models import UserType

SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')

class IsAdministrador(permissions.BasePermission):
    """
    Permiso para usuarios con tipo Administrador.
    """

    def has_permission(self, request, view):
        if request.user.is_anonymous:
            return False
        return request.user.tipo_usuario_id is not None and request.user.tipo_usuario_id == UserType.get_administrador_pk()


class IsConsultor(permissions.BasePermission):
    """
    Permiso para usuarios con tipo Consultor.
    """

    def has_permission(self, request, view):
        if request.user.is_anonymous:
            return False
        # Consultor solo tiene acceso de lectura
        return request.user.tipo_usuario_id is not None and request.user.tipo_usuario_id == UserType.get_consultor_pk()


class IsSuper(permissions.BasePermission):
    """
    Permiso para usuarios con tipo Super.
    """

    def has_permission(self, request, view):
        if request.user.is_anonymous:
            return False
        # Asegúrate de que el usuario con tipo Super tenga acceso completo
        return request.user.tipo_usuario_id is not None and request.user.tipo_usuario_id == UserType.get_super_pk()


class IsStudent(permissions.BasePermission):
    """
    Permiso para usuarios que actúan como alumno:
    tipo Estudiante puro, o cualquier tipo con el flag is_student=True.
    """

    def has_permission(self, request, view):
        if request.user.is_anonymous:
            return False
        return request.user.is_student_user


class StudentReadMixin:
    """Agrega lectura (list/retrieve) para Student a los roles del viewset,
    sin alterar quién puede escribir. Cada viewset declara `write_permission`
    con su combinación de roles actual."""
    write_permission = None

    def get_permissions(self):
        base = self.write_permission
        if self.action in ('list', 'retrieve'):
            return [(base | IsStudent)()]
        return [base()]
