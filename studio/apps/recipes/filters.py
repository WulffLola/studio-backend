import django_filters
from .models import Recipe


class RecipeFilter(django_filters.FilterSet):
    titulo = django_filters.CharFilter(lookup_expr='icontains')
    ingredientes = django_filters.CharFilter(lookup_expr='icontains')
    estado = django_filters.ChoiceFilter(choices=Recipe.ESTADO_CHOICES)

    class Meta:
        model = Recipe
        fields = ['titulo', 'ingredientes', 'estado']
