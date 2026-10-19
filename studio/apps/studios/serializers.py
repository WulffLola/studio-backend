from rest_framework import serializers
from .models import Studio


class StudioSerializer(serializers.ModelSerializer):
    # is_ready es una propiedad calculada del modelo (solo lectura):
    # no se puede setear manualmente desde la API.
    is_ready = serializers.BooleanField(read_only=True)

    class Meta:
        model = Studio
        fields = ["id", "name", "address", "is_active", "created_at", "is_ready", "deleted"]
