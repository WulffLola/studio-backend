from rest_framework_simplejwt.authentication import JWTAuthentication

from .sessions import touch_session, validate_session


class SessionJWTAuthentication(JWTAuthentication):
    """JWTAuthentication + validación de la AuthSession del token (revocación,
    máximo de 8 h, inactividad de 30 min) y registro de actividad real."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        session = validate_session(token.payload, user)
        touch_session(session, request)
        user._auth_session = session
        return user, token
