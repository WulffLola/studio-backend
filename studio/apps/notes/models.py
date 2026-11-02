from django.db import models
from ckeditor.fields import RichTextField


class Note(models.Model):
    titulo = models.CharField(max_length=200)
    descripcion = RichTextField(config_name='default')
    imagen = models.ImageField(upload_to='notas/', null=True, blank=True)
    video = models.FileField(upload_to='notas/videos/', null=True, blank=True)
    ESTADO_CHOICES = (
        ('borrador', 'Borrador'),
        ('en_pausa', 'En Pausa'),
        ('activo', 'Activo'),
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.titulo
