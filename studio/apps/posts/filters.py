import django_filters
from .models import Post


class PostFilter(django_filters.FilterSet):
    title = django_filters.CharFilter(lookup_expr='icontains')
    status = django_filters.ChoiceFilter(choices=Post.STATUS_CHOICES)

    class Meta:
        model = Post
        fields = ['title', 'status']
