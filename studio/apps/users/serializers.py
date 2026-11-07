from rest_framework import serializers
from .models import CustomUser
from apps.user_type.models import UserType
from django.contrib.auth import authenticate
from django.db import IntegrityError
from django.db.models import Q

class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ("id", "email", "name", "last_name", "dni", "tipo_usuario", "code")

class UserRegisterationSerializer(serializers.ModelSerializer):
    tipo_usuario = serializers.PrimaryKeyRelatedField(
        queryset=UserType.objects.all(),
        required=True
    )
    code = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "password",
            "name",
            "last_name",
            "email",
            "dni",
            "phone",
            "birth_date",
            "sex",
            "tipo_usuario",
            "code",
            "is_student",
            "profile_photo",
            "deleted",
        )
        # 🔒 password SOLO de entrada
        extra_kwargs = {
            "password": {"write_only": True},
            "profile_photo": {"required": False},
            "phone": {"required": False},
            "birth_date": {"required": False},
            "sex": {"required": False},
        }

    def to_representation(self, instance):
        """
        Representación segura del usuario.
        NUNCA expone password (ni siquiera hasheada).
        """
        data = super().to_representation(instance)
        request = self.context.get('request')
        photo = None
        if instance.profile_photo:
            photo = request.build_absolute_uri(instance.profile_photo.url) if request else instance.profile_photo.url

        return {
            "id": data["id"],
            "name": data["name"],
            "last_name": data["last_name"],
            "dni": data["dni"],
            "email": data["email"],
            "phone": instance.phone,
            "birth_date": instance.birth_date,
            "sex": instance.sex,
            "tipo": instance.tipo_usuario.user_type_name if instance.tipo_usuario else None,
            "code": instance.code,
            "is_student": instance.is_student,
            "profile_photo": photo,
            "deleted": instance.deleted,
        }

    def validate(self, data):
        # 🔹 SOLO en creación
        if self.instance is None:
            required_fields = ['tipo_usuario', 'name', 'last_name', 'dni', 'email']

            for field in required_fields:
                if not data.get(field):
                    raise serializers.ValidationError(
                        {field: f"El campo {field} es obligatorio."}
                    )

            # Unicidad solo en creación
            if CustomUser.all_objects.filter(dni=data['dni']).exists():
                raise serializers.ValidationError(
                    {"dni": "Este DNI ya está registrado."}
                )

            if CustomUser.all_objects.filter(email__iexact=data['email']).exists():
                raise serializers.ValidationError(
                    {"email": "Este correo electrónico ya está registrado."}
                )

        # 🔹 En update no exigimos campos que no vienen
        return data


    


class CheckDniSerializer(serializers.Serializer):
    dni = serializers.CharField()
    email = serializers.EmailField()


class RegisterNewSerializer(serializers.Serializer):
    """Registro de alumno nuevo (no está en people)."""
    dni = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    name = serializers.CharField()
    last_name = serializers.CharField()
    sex = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    birth_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        _validate_registration_password(attrs)
        return attrs


def _validate_registration_password(attrs):
    from .passwords import validate_new_password
    candidate = CustomUser(
        email=attrs.get("email", ""), dni=attrs.get("dni", ""),
        name=attrs.get("name", ""), last_name=attrs.get("last_name", ""),
    )
    validate_new_password(attrs["password"], candidate)


class RegisterExistingSerializer(serializers.Serializer):
    """Registro de alumno que ya existe en people."""
    dni = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        _validate_registration_password(attrs)
        return attrs


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    # La política de longitud/complejidad la aplican AUTH_PASSWORD_VALIDATORS en la vista.
    password = serializers.CharField(write_only=True)


class UserPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['profile_photo']

    def validate_profile_photo(self, value):
        max_mb = 5
        if value.size > max_mb * 1024 * 1024:
            raise serializers.ValidationError(f'La imagen no puede superar {max_mb} MB.')
        allowed = ('image/jpeg', 'image/png', 'image/webp')
        if hasattr(value, 'content_type') and value.content_type not in allowed:
            raise serializers.ValidationError('Formato no permitido. Usá JPG, PNG o WebP.')
        return value


class UserLoginSerializer(serializers.Serializer):
    """
    Login con identifier (email o dni) + password.
    """
    identifier = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        from django.contrib.auth.hashers import make_password
        from . import lockout

        identifier = data["identifier"]
        password = data["password"]
        request = self.context.get("request")

        # Bloqueo temporal por cuenta (email y DNI comparten contador) y por IP.
        key = lockout.account_key(identifier)
        lockout.check(request, key)

        try:
            user = CustomUser.objects.get(
                Q(email__iexact=identifier.strip()) | Q(dni=identifier.strip()),
                deleted__isnull=True,
                is_active=True,
            )
        except (CustomUser.DoesNotExist, CustomUser.MultipleObjectsReturned):
            make_password(password)  # tiempo similar al caso "existe": no revela cuentas
            lockout.register_failure(request, key)
            raise serializers.ValidationError("Credenciales incorrectas")

        if not user.check_password(password):
            lockout.register_failure(request, key)
            raise serializers.ValidationError("Credenciales incorrectas")

        lockout.register_success(key)
        return user
