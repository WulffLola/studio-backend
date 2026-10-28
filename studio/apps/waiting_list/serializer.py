from rest_framework import serializers
from .models import WaitingList
from apps.people.serializer import PersonSerializer
from apps.slots.serializer import SlotSerializer
from apps.people.models import Person
from apps.slots.models import Slot

class WaitingListSerializer(serializers.ModelSerializer):
    person_id = serializers.PrimaryKeyRelatedField(queryset=Person.objects.all(), source='person', write_only=True)
    person = PersonSerializer(read_only=True) 
    slot_id = serializers.PrimaryKeyRelatedField(queryset=Slot.objects.all(), source='slot', write_only=True)
    slot = SlotSerializer(read_only=True) 

    class Meta:
        model = WaitingList
        fields = '__all__'