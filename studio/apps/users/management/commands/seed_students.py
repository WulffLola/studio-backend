from django.core.management.base import BaseCommand

from apps.user_type.models import UserType
from apps.users.models import CustomUser

STUDENTS = [
    {
        'email': 'alumno1@test.com',
        'password': 'test1234',
        'name': 'Laura',
        'last_name': 'Gómez',
        'dni': '40123456',
    },
    {
        'email': 'alumno2@test.com',
        'password': 'test1234',
        'name': 'Marcos',
        'last_name': 'Díaz',
        'dni': '41234567',
    },
]


class Command(BaseCommand):
    help = 'Crea usuarios de tipo Estudiante para pruebas.'

    def handle(self, *args, **kwargs):
        # Tipo canónico 'Estudiante' (no crear el duplicado 'Student').
        student_type, _ = UserType.objects.get_or_create(user_type_name='Estudiante')

        for data in STUDENTS:
            if CustomUser.all_objects.filter(email=data['email']).exists():
                self.stdout.write(self.style.WARNING(f"Ya existe: {data['email']}"))
                continue

            CustomUser.objects.create_user(
                email=data['email'],
                password=data['password'],
                name=data['name'],
                last_name=data['last_name'],
                dni=data['dni'],
                tipo_usuario=student_type,
            )
            self.stdout.write(self.style.SUCCESS(f"Creado: {data['email']}"))
