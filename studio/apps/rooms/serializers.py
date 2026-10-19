from rest_framework import serializers
from .models import Room

class RoomSerializer(serializers.ModelSerializer):
    studio_name = serializers.CharField(source="studio.name", read_only=True)

    class Meta:
        model = Room
        fields = ["id", "name", "studio", "studio_name", "capacity", "is_active", "created_at", "deleted"]
