from rest_framework import serializers
from .models import HomePhrase


class HomePhraseSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomePhrase
        fields = '__all__' 
