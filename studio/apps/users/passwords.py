"""Políticas de contraseña: validadores de Django, contraseña actual y
revocación de sesiones al cambiarla."""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.response import Response

from . import lockout
from .sessions import revoke_all_sessions


def validate_new_password(password, user=None, field="password"):
    """Ejecuta AUTH_PASSWORD_VALIDATORS. ``user`` puede ser una instancia sin
    guardar (para el validador de similitud con nombre, email, DNI)."""
    try:
        validate_password(password, user=user)
    except DjangoValidationError as e:
        raise serializers.ValidationError({field: list(e.messages)})


def change_password(request, instance, new_password):
    """Cambia la contraseña de ``instance`` desde la gestión de usuarios.

    - Cambio propio (voluntario): exige ``current_password`` correcta; los
      fallos cuentan para el bloqueo de la cuenta. Se cierran las demás
      sesiones y se mantiene la actual.
    - Cambio administrativo sobre otra cuenta: no pide la contraseña actual
      (ya está autorizado por rol) y revoca todas las sesiones del usuario.

    Devuelve un Response de error o None si se aplicó.
    """
    is_self = instance.pk == request.user.pk
    if is_self:
        current = request.data.get("current_password") or ""
        key = lockout.user_key(instance)
        lockout.check(request, key)
        if not current or not instance.check_password(current):
            lockout.register_failure(request, key)
            return Response(
                {"current_password": ["La contraseña actual no es correcta."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        lockout.register_success(key)
    validate_new_password(new_password, instance)
    instance.set_password(new_password)
    instance.save()
    if is_self:
        current_session = getattr(request.user, "_auth_session", None)
        revoke_all_sessions(
            instance, "password_change",
            except_session_id=current_session.pk if current_session else None,
            bump_version=current_session is None,
        )
    else:
        revoke_all_sessions(instance, "password_change_admin")
    return None
