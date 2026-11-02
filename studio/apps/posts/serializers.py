from rest_framework import serializers
from .models import Post


class PostSerializer(serializers.ModelSerializer):
    # caption es OPCIONAL: se puede omitir, enviar "" o null. null se normaliza a ""
    # (el modelo guarda siempre un string, sin migración).
    caption = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')

    class Meta:
        model = Post
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'published_at', 'deleted_at']

    def validate_caption(self, value):
        return value or ''
