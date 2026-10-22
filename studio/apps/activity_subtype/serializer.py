from rest_framework import serializers
from .models import ActivitySubType


class PlansSubtypeInActivitySerializer(serializers.Serializer):
    """Serializer liviano para exponer plans_subtype dentro de una subactividad.
    No usa ModelSerializer para evitar acoplar imports entre apps."""
    id = serializers.IntegerField()
    name = serializers.CharField()
    sessions = serializers.IntegerField(allow_null=True)
    plan_type_name = serializers.SerializerMethodField()

    def get_plan_type_name(self, obj):
        return obj.plan_type.name if obj.plan_type_id else None


class ActivitySubTypeSerializer(serializers.ModelSerializer):
    activity_type_name = serializers.CharField(source='activity_type.name', read_only=True)
    plans_subtypes = serializers.SerializerMethodField()

    class Meta:
        model = ActivitySubType
        fields = '__all__'

    def get_plans_subtypes(self, obj):
        qs = getattr(obj, 'alive_plans_subtypes', None)
        if qs is None:
            qs = obj.plans_subtypes.filter(deleted__isnull=True)
        return PlansSubtypeInActivitySerializer(qs, many=True).data
