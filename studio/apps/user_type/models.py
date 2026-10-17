from django.db import models

class UserType(models.Model):
    user_type_name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.user_type_name

    @classmethod
    def get_super_pk(cls):
        try:
            return cls.objects.get(user_type_name='Super').id
        except cls.DoesNotExist:
            return None 

    @classmethod
    def get_administrador_pk(cls):
        try:
            return cls.objects.get(user_type_name='Administrador').id
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_consultor_pk(cls):
        try:
            return cls.objects.get(user_type_name='Consultor').id
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_student_pk(cls):
        """
        Tipo de usuario para alumnos del portal (Estudiante).
        """
        try:
            return cls.objects.get(user_type_name="Estudiante").id
        except cls.DoesNotExist:
            return None