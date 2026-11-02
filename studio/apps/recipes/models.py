from django.db import models
from ckeditor.fields import RichTextField


class Recipe(models.Model):
    titulo = models.CharField(max_length=200)
    descripcion = RichTextField()
    ingredientes = models.TextField()
    pasos = models.TextField()
    imagen = models.ImageField(upload_to='recipes/', null=True, blank=True)
    video = models.FileField(upload_to='recipes/videos/', null=True, blank=True)
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
