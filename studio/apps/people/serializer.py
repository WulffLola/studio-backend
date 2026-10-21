from rest_framework import serializers
from .models import Person, PersonActivePlan
from apps.plans_subtype.models import PlansSubtype
from apps.plans_subtype.serializer import PlansSubtypeSerializer
from apps.sworn_statement.serializer import PersonSwornStatementInlineSerializer


class PersonActivePlanSerializer(serializers.ModelSerializer):
    plans_subtype = PlansSubtypeSerializer(read_only=True)
    plans_subtype_id = serializers.PrimaryKeyRelatedField(
        queryset=PlansSubtype.objects.all(), source='plans_subtype', write_only=True
    )

    class Meta:
        model = PersonActivePlan
        fields = '__all__'


class PersonSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    sworn_statements = PersonSwornStatementInlineSerializer(many=True, read_only=True)

    class Meta:
        model = Person
        fields = '__all__'
        read_only_fields = ['firmo_declaracion_general']


class PersonWithPlansSerializer(PersonSerializer):
    """Igual que PersonSerializer pero embebe los planes activos del alumno.
    Se usa SOLO en /people/ para no inflar los serializers donde Person va anidado."""
    active_plans = PersonActivePlanSerializer(many=True, read_only=True)

    class Meta(PersonSerializer.Meta):
        pass


class PersonPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = ['profile_photo']

    def validate_profile_photo(self, value):
        max_mb = 5
        if value.size > max_mb * 1024 * 1024:
            raise serializers.ValidationError(f'La imagen no puede superar {max_mb} MB.')
        allowed = ('image/jpeg', 'image/png', 'image/webp')
        if hasattr(value, 'content_type') and value.content_type not in allowed:
            raise serializers.ValidationError('Formato no permitido. Usá JPG, PNG o WebP.')
        return value
