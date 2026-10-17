from rest_framework import status, viewsets, views
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.user_type.permisos import IsSuper, IsAdministrador, IsStudent
from apps.user_type.models import UserType
from . import serializers
from apps.users.models import CustomUser
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from apps.users.serializers import (
    UserRegisterationSerializer,
    UserPhotoSerializer,
    CheckDniSerializer,
    RegisterNewSerializer,
    RegisterExistingSerializer,
    PasswordResetSerializer,
    PasswordResetConfirmSerializer,
)
import django_filters.rest_framework
from django.db import IntegrityError, transaction
from django.core import signing
import logging

from .email_service import send_verification_email, send_password_reset_email

logger = logging.getLogger(__name__)


def _mask_phone(phone: str) -> str:
    """Enmascara el teléfono mostrando solo los últimos 4 dígitos."""
    if not phone or len(phone) < 4:
        return phone or ''
    return '*' * (len(phone) - 4) + phone[-4:]


User = get_user_model()


class UserRegistrationViewSet(viewsets.ModelViewSet):
    """
    Endpoint para crear, listar, editar y eliminar usuarios con soft delete.
    """
    queryset = CustomUser.objects.filter(deleted__isnull=True)  # Excluir usuarios eliminados
    serializer_class = UserRegisterationSerializer
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    filterset_fields = ["name", "last_name", "dni", "tipo_usuario"]

    def get_permissions(self):
        if self.action in ('retrieve', 'update', 'partial_update', 'upload_photo'):
            return [(IsSuper | IsAdministrador | IsStudent)()]
        return [(IsSuper | IsAdministrador)()]

    def get_queryset(self):
        user = self.request.user
        user_tipo = user.tipo_usuario

        # Guard: usuario autenticado sin tipo (tipo_usuario nullable) no debe
        # reventar el dereference de .id más abajo; si no es superuser, no ve nada.
        if user_tipo is None and not user.is_superuser:
            return CustomUser.objects.none()

        # Super: ve todos (incluye soft-deleted)
        if user.is_superuser or user_tipo.id == UserType.get_super_pk():
            return CustomUser.all_objects.all()

        # Admin: ve Admin, Consultant y Student (solo activos)
        if user_tipo.id == UserType.get_administrador_pk():
            allowed = [
                UserType.get_administrador_pk(),
                UserType.get_consultor_pk(),
                UserType.get_student_pk(),
            ]
            return CustomUser.objects.filter(tipo_usuario__id__in=allowed)

        # Consultant: SOLO lectura de Students
        if user_tipo.id == UserType.get_consultor_pk():
            return CustomUser.objects.filter(
                tipo_usuario__id=UserType.get_student_pk()
            )

        # Student: sólo su propia fila (self-service).
        if user_tipo and user_tipo.id == UserType.get_student_pk():
            return CustomUser.objects.filter(pk=user.pk)

        # Otros: no listan acá
        return CustomUser.objects.none()


    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        user_tipo = user.tipo_usuario

        # Guard: usuario autenticado sin tipo (tipo_usuario nullable) no debe
        # reventar el dereference de .id más abajo.
        if user_tipo is None and not user.is_superuser:
            return Response({"detail": "No tienes permisos para ver este usuario."},
                            status=status.HTTP_403_FORBIDDEN)

        # Super: ve cualquiera
        if user.is_superuser or user_tipo.id == UserType.get_super_pk():
            return Response(self.get_serializer(instance).data)

        # Admin: ve Admin, Consultant y Student
        if user_tipo.id == UserType.get_administrador_pk():
            if instance.tipo_usuario.id in [
                UserType.get_administrador_pk(),
                UserType.get_consultor_pk(),
                UserType.get_student_pk(),
            ]:
                return Response(self.get_serializer(instance).data)
            return Response(
                {"detail": "No tienes permisos para ver este usuario."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Consultant: SOLO ver Students
        if user_tipo.id == UserType.get_consultor_pk():
            if instance.tipo_usuario.id == UserType.get_student_pk():
                return Response(self.get_serializer(instance).data)
            return Response(
                {"detail": "No tienes permisos para ver este usuario."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Student: sólo su propia fila.
        if user_tipo.id == UserType.get_student_pk():
            if instance.id == user.id:
                return Response(self.get_serializer(instance).data)
            # Defensa en profundidad: get_queryset ya restringe a la fila propia (404 antes); esto cubre cambios futuros.
            return Response({"detail": "No tienes permisos para ver este usuario."},
                            status=status.HTTP_403_FORBIDDEN)

        return Response(
            {"detail": "No tienes permisos para ver este usuario."},
            status=status.HTTP_403_FORBIDDEN,
        )




    def create(self, request, *args, **kwargs):
        """
        Crear un nuevo usuario (gestión interna).
        Admin puede crear Admin, Consultor y Estudiante.
        Super puede crear cualquier tipo.
        """
        data = request.data.copy()
        tipo_usuario = data.get("tipo_usuario")

        if not tipo_usuario:
            return Response(
                {"detail": "El campo tipo_usuario es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Admin: puede crear Admin, Consultor y Estudiante
        if request.user.tipo_usuario.id != UserType.get_super_pk():
            allowed_user_types = [
                UserType.get_administrador_pk(),
                UserType.get_consultor_pk(),
                UserType.get_student_pk(),
            ]
            if int(tipo_usuario) not in allowed_user_types:
                return Response(
                    {"detail": "No tienes permisos para crear este tipo de usuario."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # 🔐 Encriptar password
        if "password" in data:
            data["password"] = make_password(data["password"])

        serializer = self.get_serializer(data=data)

        try:
            serializer.is_valid(raise_exception=True)
            # Usuarios creados por admin/super quedan activos directamente
            user = serializer.save(is_active=True)

            token = RefreshToken.for_user(user)
            response_data = serializer.data
            response_data["tokens"] = {
                "refresh": str(token),
                "access": str(token.access_token),
            }
            return Response(response_data, status=status.HTTP_201_CREATED)

        except IntegrityError as e:
            if "email" in str(e):
                return Response(
                    {"email": "Este correo electrónico ya está registrado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if "dni" in str(e):
                return Response(
                    {"dni": "Este DNI ya está registrado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {"detail": "Error al crear el usuario."},
                status=status.HTTP_400_BAD_REQUEST,
            )


    def update(self, request, *args, **kwargs):
        """
        Actualizar un usuario existente.
        """
        instance = self.get_object()
        data = request.data.copy()
        tipo_usuario = data.get('tipo_usuario')
        user = request.user
        user_tipo = user.tipo_usuario

        # Guard: usuario autenticado sin tipo (tipo_usuario nullable) no debe
        # reventar el dereference de .id más abajo.
        if user_tipo is None and not user.is_superuser:
            return Response({"detail": "No tienes permisos para actualizar este usuario."},
                            status=status.HTTP_403_FORBIDDEN)

        # Super: acceso total, sin restricciones de tipo (evaluado primero:
        # un usuario is_superuser nunca debe caer en las ramas más restrictivas).
        if user.is_superuser or user_tipo.id == UserType.get_super_pk():
            pass

        # Admin: no puede asignar rol Super, y sólo edita filas Admin/Consultor.
        elif user_tipo.id == UserType.get_administrador_pk():
            if tipo_usuario and int(tipo_usuario) == UserType.get_super_pk():
                return Response(
                    {"detail": "No tienes permisos para asignar el rol Super a este usuario."},
                    status=status.HTTP_403_FORBIDDEN
                )
            allowed_user_types = [UserType.get_administrador_pk(), UserType.get_consultor_pk()]
            new_tipo = int(tipo_usuario) if tipo_usuario is not None else instance.tipo_usuario.id
            if instance.tipo_usuario.id not in allowed_user_types or new_tipo not in allowed_user_types:
                return Response(
                    {"detail": "No tienes permisos para actualizar este usuario."},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Student: sólo su propia fila y sólo campos de perfil básicos (whitelist).
        elif user_tipo.id == UserType.get_student_pk():
            if instance.id != user.id:
                # Defensa en profundidad: get_queryset ya restringe a la fila propia (404 antes); esto cubre cambios futuros.
                return Response({"detail": "No tienes permisos para actualizar este usuario."},
                                status=status.HTTP_403_FORBIDDEN)
            ALLOWED_STUDENT_FIELDS = {'name', 'last_name', 'phone', 'birth_date', 'sex', 'email', 'password'}
            # Campos fuera de la whitelist (tipo_usuario, deleted, is_student, is_*): 403.
            forbidden = set(data.keys()) - ALLOWED_STUDENT_FIELDS
            if forbidden:
                return Response(
                    {"detail": f"No podés modificar estos campos: {sorted(forbidden)}."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if "password" in data:
                if data["password"]:
                    instance.set_password(data["password"])
                    instance.save()
                data.pop("password", None)
            serializer = self.get_serializer(instance, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            instance.refresh_from_db()
            return Response(self.get_serializer(instance).data, status=status.HTTP_200_OK)

        # Cualquier otro rol no contemplado (p.ej. Consultor, o un híbrido raro): 403.
        else:
            return Response(
                {"detail": "No tienes permisos para actualizar este usuario."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Flujo genérico (Super y Admin válidos llegan acá).
        # Manejo del campo 'password'
        if "password" in data:
            if data["password"]:
                instance.set_password(data["password"])
                instance.save()
            data.pop("password", None)

        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        instance.refresh_from_db()

        return Response(self.get_serializer(instance).data, status=status.HTTP_200_OK)



    def destroy(self, request, *args, **kwargs):
        """
        Eliminar (soft delete) un usuario.
        """
        instance = self.get_object()

        # Super puede eliminar cualquiera
        if request.user.tipo_usuario.id == UserType.get_super_pk():
            instance.deleted = timezone.now()
            instance.save()
            return Response(status=status.HTTP_204_NO_CONTENT)

        # Admin puede eliminar Admin, Consultor y Student
        if request.user.tipo_usuario.id == UserType.get_administrador_pk():
            allowed_user_types = [
                UserType.get_administrador_pk(),
                UserType.get_consultor_pk(),
                UserType.get_student_pk(),
            ]
            if instance.tipo_usuario.id not in allowed_user_types:
                return Response(
                    {"detail": "No tienes permisos para eliminar este usuario."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            instance.deleted = timezone.now()
            instance.save()
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(
            {"detail": "No tienes permisos para eliminar este usuario."},
            status=status.HTTP_403_FORBIDDEN,
        )

    @action(detail=True, methods=['patch'], url_path='upload-photo')
    def upload_photo(self, request, pk=None):
        user = self.get_object()
        serializer = UserPhotoSerializer(user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'profile_photo': request.build_absolute_uri(user.profile_photo.url)},
            status=status.HTTP_200_OK,
        )


class UserLoginViewSet(viewsets.ViewSet):
    """
    Endpoint de login con email o DNI.
    """
    permission_classes = [AllowAny]

    def create(self, request):
        serializer = serializers.UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data

        token = RefreshToken.for_user(user)

        request = self.request
        profile_photo_url = None
        if user.profile_photo:
            profile_photo_url = request.build_absolute_uri(user.profile_photo.url)

        data = {
            "id": user.id,
            "email": user.email,
            "dni": user.dni,
            "name": user.name,
            "last_name": user.last_name,
            "code": user.code,
            "profile_photo": profile_photo_url,
            "tipo": user.tipo_usuario.user_type_name if user.tipo_usuario else None,
            "tokens": {
                "refresh": str(token),
                "access": str(token.access_token),
            },
        }

        return Response(data, status=status.HTTP_200_OK)


class StudentLoginViewSet(viewsets.ViewSet):
    """
    POST /student-login/
    Login exclusivo para usuarios de tipo Estudiante.
    Rechaza cualquier otro tipo de usuario aunque las credenciales sean válidas.
    """
    permission_classes = [AllowAny]

    def create(self, request):
        serializer = serializers.UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data

        if not user.is_student_user:
            return Response(
                {"detail": "Acceso denegado. Este portal es exclusivo para estudiantes."},
                status=status.HTTP_403_FORBIDDEN,
            )

        token = RefreshToken.for_user(user)
        profile_photo_url = None
        if user.profile_photo:
            profile_photo_url = request.build_absolute_uri(user.profile_photo.url)

        return Response({
            "id": user.id,
            "email": user.email,
            "dni": user.dni,
            "name": user.name,
            "last_name": user.last_name,
            "person_id": user.person_id,
            "profile_photo": profile_photo_url,
            "tipo": user.tipo_usuario.user_type_name if user.tipo_usuario else None,
            "tokens": {
                "refresh": str(token),
                "access": str(token.access_token),
            },
        }, status=status.HTTP_200_OK)


class UserLogoutViewSet(views.APIView):
    """
    An endpoint to logout users.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if self.request.data.get('all'):
            for token in OutstandingToken.objects.filter(user=request.user):
                _, _ = BlacklistedToken.objects.get_or_create(token=token)
            return Response({"status": "OK, goodbye, all refresh tokens blacklisted"})
        refresh_token = self.request.data.get('refresh_token')
        token = RefreshToken(token=refresh_token)
        token.blacklist()
        return Response({"status": "OK, goodbye"})


# Helpers de envío externo

def _send_verification_wp(phone, name, token):
    import os
    import requests
    url = os.getenv("API_WPP_VERIFY")
    if not url:
        logger.warning("API_WPP_VERIFY not configured — skipping WP send")
        return
    try:
        requests.post(url, json={"phone": phone, "name": name, "token": token}, timeout=5)
    except requests.RequestException as e:
        logger.error(f"Failed to send WP verification: {e}")


# Registro público

class CheckDniView(viewsets.ViewSet):
    """
    POST /register/check/
    Verifica si el DNI/email ya tienen usuario registrado y si el DNI existe en people.

    Respuestas posibles:
      - {result: "already_registered"}         -> DNI o email ya tiene cuenta -> ir a login
      - {result: "not_found"}                  -> DNI no está en people ni en users -> registro nuevo
      - {result: "email_mismatch"}             -> DNI en people pero email no coincide
      - {result: "found", person: {...}}       -> DNI en people y email coincide -> registro con datos precargados
    """
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        from apps.people.models import Person

        serializer = CheckDniSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dni = serializer.validated_data['dni']
        email = serializer.validated_data['email']

        student_pk = UserType.get_student_pk()

        # 1. ¿Ya existe un ESTUDIANTE con ese DNI o ese email?
        dni_user   = CustomUser.all_objects.filter(dni=dni, tipo_usuario_id=student_pk).first()
        email_user = CustomUser.all_objects.filter(email__iexact=email, tipo_usuario_id=student_pk).first()

        dni_taken   = dni_user is not None
        email_taken = email_user is not None

        if dni_taken or email_taken:
            # Detectar si la cuenta está dada de baja (soft-deleted)
            account_deleted = any(
                u is not None and u.deleted is not None
                for u in [dni_user, email_user]
            )
            if account_deleted:
                return Response(
                    {
                        "result": "account_disabled",
                        "detail": "Tu cuenta fue dada de baja. Contactá al estudio para reactivarla.",
                    },
                    status=status.HTTP_200_OK,
                )
            return Response(
                {
                    "result": "already_registered",
                    "dni_taken": dni_taken,
                    "email_taken": email_taken,
                    "detail": "Ya existe una cuenta con esos datos. Iniciá sesión.",
                },
                status=status.HTTP_200_OK,
            )

        # 2. ¿El email pertenece a otro alumno en people (distinto DNI)?
        if Person.all_objects.filter(email__iexact=email, deleted__isnull=True).exclude(dni=dni).exists():
            return Response(
                {
                    "result": "email_in_use",
                    "detail": "El email ya está registrado para otro alumno. "
                              "Revisá el email ingresado o contactá al estudio.",
                },
                status=status.HTTP_200_OK,
            )

        # 3. ¿Está el DNI en la tabla de alumnos (people)?
        person = Person.all_objects.filter(dni=dni, deleted__isnull=True).first()

        if not person:
            return Response({"result": "not_found"}, status=status.HTTP_200_OK)

        if (person.email or '').lower() != email.lower():
            return Response(
                {
                    "result": "email_mismatch",
                    "detail": "El email no coincide con el registrado. "
                              "Revisá el email ingresado o contactá al estudio.",
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "result": "found",
                "person": {
                    "name": person.name,
                    "last_name": person.last_name,
                    "sex": person.sex,
                    "birth_date": person.birth_date,
                    "email": person.email,
                    "phone": _mask_phone(person.phone or ''),
                },
            },
            status=status.HTTP_200_OK,
        )


class RegisterView(viewsets.ViewSet):
    """
    POST /register/
    Crea un CustomUser de tipo Student.

    Caso A — alumno nuevo (DNI no existe en people):
      Requiere: dni, email, password, name, last_name  (+ sex, phone, birth_date opcionales)
      Crea Person + CustomUser, envía email + WP.

    Caso B — alumno existente (DNI ya está en people):
      Requiere: dni, email, password
      Re-valida email, crea solo CustomUser vinculado al Person, envía email.
    """
    permission_classes = [AllowAny]
    # TODO: USE MODELVIEWSET CON DOS SERIALIZERS DISTINTOS PARA CADA CASO (nuevo vs existente) EN LUGAR DE VALIDAR DENTRO DEL CREATE

    def create(self, request, *args, **kwargs):
        from apps.people.models import Person

        dni = request.data.get('dni', '').strip()
        email = request.data.get('email', '').strip()

        # Verificar que no exista ya un ESTUDIANTE con esos datos
        student_pk = UserType.get_student_pk()
        email_user = CustomUser.all_objects.filter(email__iexact=email, tipo_usuario_id=student_pk).first()
        dni_user   = CustomUser.all_objects.filter(dni=dni, tipo_usuario_id=student_pk).first()

        if email_user is not None or dni_user is not None:
            account_deleted = any(
                u is not None and u.deleted is not None
                for u in [email_user, dni_user]
            )
            if account_deleted:
                return Response(
                    {"detail": "Tu cuenta fue dada de baja. Contactá al estudio para reactivarla."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {"detail": "Ya existe un usuario con esos datos. Iniciá sesión."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        person = Person.all_objects.filter(dni=dni, deleted__isnull=True).first()

        # La creación va en una transacción: si el email colisiona con un usuario
        # de otro tipo (Admin/Consultor) —que el precheck, scoped a Estudiante, no
        # detecta— el unique de DB lanza IntegrityError. Lo capturamos para devolver
        # 400 (antes daba 500) y para no dejar un Person huérfano.
        notify_phone = None
        try:
            with transaction.atomic():
                if person:
                    # Caso B: alumno existente
                    serializer = RegisterExistingSerializer(data=request.data)
                    serializer.is_valid(raise_exception=True)

                    if (person.email or '').lower() != email.lower():
                        return Response(
                            {"detail": "El email no coincide con el registrado para ese DNI."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    user = self._create_student(
                        email=email,
                        password=serializer.validated_data['password'],
                        name=person.name or '',
                        last_name=person.last_name or '',
                        dni=dni,
                        person=person,
                    )
                    notify_name = person.name or ''

                else:
                    # Caso A: alumno nuevo
                    serializer = RegisterNewSerializer(data=request.data)
                    serializer.is_valid(raise_exception=True)
                    d = serializer.validated_data

                    person = Person.objects.create(
                        dni=d['dni'],
                        email=d['email'],
                        name=d['name'],
                        last_name=d['last_name'],
                        sex=d.get('sex', ''),
                        phone=d.get('phone', ''),
                        birth_date=d.get('birth_date'),
                    )
                    user = self._create_student(
                        email=email,
                        password=d['password'],
                        name=d['name'],
                        last_name=d['last_name'],
                        dni=dni,
                        person=person,
                    )
                    notify_name = d['name']
                    notify_phone = person.phone or ''

                token_str = signing.dumps(user.pk, salt='email-verification')
        except IntegrityError:
            return Response(
                {"detail": "Ya existe un usuario con ese email o DNI."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Notificaciones fuera de la transacción: el usuario ya quedó creado, no
        # queremos que un fallo de email/WhatsApp revierta el alta.
        send_verification_email(email, notify_name, token_str)
        if notify_phone is not None:
            _send_verification_wp(notify_phone, notify_name, token_str)

        return Response(
            {"detail": "Usuario creado. Revisá tu email para activar tu cuenta."},
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _create_student(email, password, name, last_name, dni, person):
        student_type, _ = UserType.objects.get_or_create(user_type_name='Estudiante')
        user = CustomUser(
            email=email,
            name=name,
            last_name=last_name,
            dni=dni,
            tipo_usuario=student_type,
            person=person,
            is_active=False,
        )
        user.set_password(password)
        user.save()
        return user


class VerifyEmailView(viewsets.ViewSet):
    """
    POST /register/verify-email/
    Body: {token}
    Activa el usuario y devuelve JWT tokens.
    """
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        token_str = request.data.get('token')
        if not token_str:
            return Response(
                {"detail": "Se requiere el campo 'token'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_pk = signing.loads(
                token_str,
                salt='email-verification',
                max_age=86400,  # 24 horas
            )
        except signing.SignatureExpired:
            return Response(
                {"detail": "El token de verificación expiró. Solicitá uno nuevo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except signing.BadSignature:
            return Response(
                {"detail": "Token inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = CustomUser.all_objects.get(pk=user_pk)
        except CustomUser.DoesNotExist:
            return Response({"detail": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if user.is_active:
            return Response(
                {"detail": "La cuenta ya estaba verificada."},
                status=status.HTTP_200_OK,
            )

        user.is_active = True
        user.save(update_fields=['is_active'])

        jwt_token = RefreshToken.for_user(user)
        return Response(
            {
                "detail": "Cuenta verificada exitosamente.",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "last_name": user.last_name,
                    "dni": user.dni,
                },
                "tokens": {
                    "refresh": str(jwt_token),
                    "access": str(jwt_token.access_token),
                },
            },
            status=status.HTTP_200_OK,
        )


# Recuperación de contraseña

class PasswordResetView(viewsets.ViewSet):
    """
    POST /password-reset/
    Body: {email}
    Genera un token firmado (TTL 1 h) y llama a API_EMAIL_RESET.
    Siempre responde 200 para no revelar si el email existe.
    """
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        user = CustomUser.objects.filter(email__iexact=email, is_active=True).first()
        if user:
            token_str = signing.dumps(user.pk, salt='password-reset')
            send_password_reset_email(email, user.name, token_str)

        return Response(
            {"detail": "Si el email está registrado, recibirás instrucciones para restablecer tu contraseña."},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(viewsets.ViewSet):
    """
    POST /password-reset/confirm/
    Body: {token, password}
    Valida el token (TTL 1 h) y establece la nueva contraseña.
    """
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token_str = serializer.validated_data['token']
        new_password = serializer.validated_data['password']

        try:
            user_pk = signing.loads(token_str, salt='password-reset', max_age=3600)
        except signing.SignatureExpired:
            return Response(
                {"detail": "El enlace de recuperación expiró. Solicitá uno nuevo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except signing.BadSignature:
            return Response(
                {"detail": "Token inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = CustomUser.objects.get(pk=user_pk, is_active=True)
        except CustomUser.DoesNotExist:
            return Response(
                {"detail": "Usuario no encontrado o inactivo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save(update_fields=['password'])

        return Response(
            {"detail": "Contraseña restablecida exitosamente."},
            status=status.HTTP_200_OK,
        )
