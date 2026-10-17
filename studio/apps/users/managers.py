# apps/users/managers.py
from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    """
    Manager por defecto: devuelve solo usuarios activos (no soft-deleted).
    Además define create_user / create_superuser usando email como identificador.
    """

    def get_queryset(self):
        # Solo usuarios que NO están soft-deleted
        return super().get_queryset().filter(deleted__isnull=True)

    def create_user(self, email, name, last_name, password=None, **extra_fields):
        if not email:
            raise ValueError(_("Users must have an email"))

        # La normalización a minúsculas del email (unicidad case-insensitive,
        # se centraliza en CustomUser.save(); acá solo normalizamos el
        # dominio con el helper estándar de Django.
        email = self.normalize_email(email)
        user = self.model(
            email=email,
            name=name,
            last_name=last_name,
            **extra_fields,
        )
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, name, last_name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self.create_user(email, name, last_name, password, **extra_fields)


class AllUsersManager(BaseUserManager):
    """
    Manager para incluir también usuarios soft-deleted.
    Ideal para vistas de administración (Super/Admin).
    """

    def get_queryset(self):
        # NO filtra por deleted
        return super().get_queryset()
