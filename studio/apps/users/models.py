from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from apps.user_type.models import UserType
from django.utils.timezone import now

from .managers import CustomUserManager, AllUsersManager  # 👈 importa los nuevos managers


class CustomUser(AbstractUser):
    username = None
    email = models.EmailField("email address", unique=True)
    name = models.CharField(max_length=100, blank=False)
    last_name = models.CharField(max_length=100, blank=False)
    dni = models.CharField(max_length=100, blank=False, unique=True)
    tipo_usuario = models.ForeignKey("user_type.UserType", on_delete=models.CASCADE, null=True)
    person = models.ForeignKey(
        'people.Person', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='user',
    )
    code = models.CharField(max_length=4, blank=True)
    phone = models.CharField(max_length=30, blank=True, default='')
    birth_date = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=20, blank=True, default='')
    profile_photo = models.ImageField(upload_to='users/photos/', null=True, blank=True)
    is_student = models.BooleanField(default=False)
    deleted = models.DateTimeField(null=True, blank=True)

    @property
    def is_student_user(self):
        """True si el usuario actúa como alumno: tipo Estudiante o flag is_student activado."""
        from apps.user_type.models import UserType
        return self.tipo_usuario_id == UserType.get_student_pk() or self.is_student

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["dni", "name", "last_name"]

    class Meta(AbstractUser.Meta):
        constraints = [
            # Unicidad de email case-insensitive garantizada a nivel DB (índice
            # funcional). El unique=True del campo es case-sensitive y no alcanza;
            # esto frena colisiones aunque se escriba con distinto casing por una
            # ruta que bypassee CustomUser.save() (update/bulk_create).
            models.UniqueConstraint(Lower('email'), name='user_email_ci_unique'),
        ]

    objects = CustomUserManager()     # solo activos (deleted is null)
    all_objects = AllUsersManager()   # todos, incluidos soft-deleted

    def save(self, *args, **kwargs):
        # Normalizar el email a minúsculas en TODOS los paths de creación/edición
        # (autorregistro, alta admin, seed, etc.) para que la unicidad de email sea
        # realmente case-insensitive. Es el único choke point común: RegisterView y
        # el serializer de admin construyen el CustomUser sin pasar por create_user.
        if self.email:
            self.email = self.email.strip().lower()
        if not self.code and self.dni:
            self.code = self.dni[-4:]  # Use the last 4 digits of DNI for the code
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        self.deleted = now()
        self.save(update_fields=['deleted'])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.deleted = None
        self.save(update_fields=['deleted'])
