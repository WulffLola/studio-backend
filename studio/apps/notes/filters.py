import django_filters
from .models import Note


class NoteFilter(django_filters.FilterSet):
    titulo = django_filters.CharFilter(lookup_expr='icontains')
    estado = django_filters.ChoiceFilter(choices=Note.ESTADO_CHOICES)

    class Meta:
        model = Note
        fields = ['titulo', 'estado']
