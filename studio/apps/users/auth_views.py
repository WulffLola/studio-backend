"""Endpoints de sesión: refresh con rotación, logout, estado de sesión y /token/."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers, status, views
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from .models import AuthSession
from .sessions import (
    SessionInvalid, _bind, idle_timeout, revoke_all_sessions, revoke_session,
    token_pair, validate_session,
)

# Un refresh ya rotado que vuelve a presentarse dentro de esta ventana se
# considera una carrera legítima (dos pestañas / peticiones simultáneas) y solo
# se rechaza; fuera de la ventana se trata como reutilización y se revoca la sesión.
REFRESH_REUSE_GRACE = timedelta(seconds=30)

User = get_user_model()


class _NoAuthMixin:
    """Vistas públicas que identifican al usuario por el token del body: sin
    autenticación previa, pero respondiendo 401 (no 403) ante tokens inválidos."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_authenticate_header(self, request):
        return 'Bearer realm="api"'


def _user_from_payload(payload):
    try:
        return User.objects.get(pk=payload.get("user_id"), is_active=True)
    except User.DoesNotExist:
        return None


def _decode_refresh_unverified(raw):
    """Firma verificada, pero sin chequear vencimiento ni blacklist."""
    try:
        return RefreshToken(raw, verify=False)
    except TokenError:
        return None


class _RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class SessionTokenRefreshView(_NoAuthMixin, views.APIView):
    """POST /token/refresh/  {refresh} -> {access, refresh, session_expires_at}

    Rota el refresh (el anterior queda en la blacklist). No cuenta como
    actividad del usuario: una sesión inactiva no se puede mantener viva
    renovando tokens.
    """
    def post(self, request, *args, **kwargs):
        ser = _RefreshSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        raw = ser.validated_data["refresh"]

        try:
            refresh = RefreshToken(raw)
        except TokenError:
            self._handle_reuse(raw)
            raise SessionInvalid("El token de renovación no es válido o expiró.", "token_not_valid")

        user = _user_from_payload(refresh.payload)
        if user is None:
            raise SessionInvalid("El token de renovación no es válido o expiró.", "token_not_valid")
        session = validate_session(refresh.payload, user)

        refresh.blacklist()
        refresh.set_jti()
        refresh.set_exp()
        _bind(refresh, session, user)
        return Response(token_pair(refresh, session), status=status.HTTP_200_OK)

    @staticmethod
    def _handle_reuse(raw):
        tok = _decode_refresh_unverified(raw)
        if tok is None:
            return
        jti = tok.payload.get("jti")
        bl = BlacklistedToken.objects.filter(token__jti=jti).first()
        if bl is None:
            return  # vencido, no reutilizado
        if timezone.now() - bl.blacklisted_at <= REFRESH_REUSE_GRACE:
            return  # carrera entre pestañas: solo se rechaza
        sid = tok.payload.get("sid")
        session = AuthSession.objects.filter(pk=sid).first() if sid else None
        if session is not None:
            revoke_session(session, "refresh_reuse")


class LogoutView(_NoAuthMixin, views.APIView):
    """POST /logout/  {refresh_token, all?}

    Revoca la sesión del token (los access emitidos para ella dejan de servir
    al instante) y pone el refresh en la blacklist. Funciona aunque el access
    ya haya vencido: identifica la sesión por el refresh. Con ``all`` revoca
    todas las sesiones del usuario (token_version + 1).
    """
    def post(self, request, *args, **kwargs):
        raw_refresh = request.data.get("refresh_token") or request.data.get("refresh")
        want_all = str(request.data.get("all", "")).lower() in ("1", "true", "yes", "on")

        user, sid, verified = None, None, False

        # 1) Access token del header (si sigue siendo válido)
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if header.startswith("Bearer "):
            try:
                access = AccessToken(header.split(" ", 1)[1].strip())
                user = _user_from_payload(access.payload)
                sid = access.payload.get("sid")
                verified = user is not None
            except TokenError:
                pass

        # 2) Refresh del body
        refresh = None
        if raw_refresh:
            try:
                refresh = RefreshToken(raw_refresh)
                verified = True
            except TokenError:
                refresh = _decode_refresh_unverified(raw_refresh)
            if refresh is not None:
                r_user = _user_from_payload(refresh.payload)
                if user is None:
                    user = r_user
                elif r_user is not None and r_user.pk != user.pk:
                    refresh = None  # tokens de distintos usuarios: se ignora el refresh
                sid = sid or (refresh.payload.get("sid") if refresh is not None else None)

        if user is None:
            return Response({"detail": "No se pudo identificar la sesión."}, status=status.HTTP_401_UNAUTHORIZED)

        if want_all:
            if not verified:
                return Response({"detail": "Token inválido o vencido."}, status=status.HTTP_401_UNAUTHORIZED)
            revoke_all_sessions(user, "logout_all")
            return Response({"status": "OK, goodbye, all sessions revoked"})

        if sid:
            session = AuthSession.objects.filter(pk=sid, user=user).first()
            if session is not None:
                revoke_session(session, "logout")
        if refresh is not None:
            try:
                refresh.blacklist()
            except Exception:
                pass
        return Response({"status": "OK, goodbye"})


class SessionStatusView(views.APIView):
    """GET /session/ — estado de la sesión actual. Al pasar por la autenticación
    registra la actividad informada en X-Client-Idle (el frontend lo usa como
    'ping' solo cuando hubo interacción real del usuario)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        session = getattr(request.user, "_auth_session", None)
        if session is None:
            return Response({"detail": "Sin sesión JWT."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "session_expires_at": session.expires_at.isoformat(),
            "last_activity_at": session.last_activity_at.isoformat(),
            "idle_timeout_seconds": int(idle_timeout().total_seconds()),
        })


class TokenObtainView(_NoAuthMixin, views.APIView):
    """POST /token/  {email|identifier, password} -> {refresh, access, session_expires_at}

    Reemplaza a TokenObtainPairView de simplejwt manteniendo su contrato
    (mismos campos de entrada y de salida) pero emitiendo tokens ligados a una
    AuthSession y aplicando las mismas reglas que /login/.
    """
    def post(self, request, *args, **kwargs):
        from .serializers import UserLoginSerializer
        from .sessions import issue_tokens
        data = {
            "identifier": request.data.get("identifier") or request.data.get("email") or "",
            "password": request.data.get("password") or "",
        }
        ser = UserLoginSerializer(data=data, context={"request": request})
        ser.is_valid(raise_exception=True)
        tokens, _ = issue_tokens(ser.validated_data, request)
        return Response(tokens, status=status.HTTP_200_OK)
