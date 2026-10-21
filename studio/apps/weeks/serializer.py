from rest_framework import serializers
from .models import Week


class WeekSerializer(serializers.ModelSerializer):

    class Meta:
        model = Week
        fields = '__all__'