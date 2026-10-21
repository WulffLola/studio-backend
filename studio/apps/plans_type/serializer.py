from django.db.models import Prefetch
from rest_framework import serializers
from .models import PlansType, ComboPlanDiscount, PlanDiscount


class PlansTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlansType
        fields = '__all__'


# Serializer de subtype con contexto del tipo padre, usado dentro de combos
class ComboSubtypeSerializer(serializers.ModelSerializer):
    plans_type_name = serializers.CharField(source='plan_type.name', read_only=True)

    class Meta:
        from apps.plans_subtype.models import PlansSubtype
        model = PlansSubtype
        fields = ['id', 'name', 'plans_type_name']


class ComboPlanDiscountSerializer(serializers.ModelSerializer):
    # Lectura: subtypes anidados con nombre del tipo padre
    plans = ComboSubtypeSerializer(many=True, read_only=True)
    # Escritura: lista de IDs enteros — evita import circular con plans_subtype
    # y el assert de DRF que falla cuando queryset=None en la definición de clase.
    plans_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        write_only=True,
    )

    class Meta:
        model = ComboPlanDiscount
        fields = ['id', 'name', 'plans', 'plans_ids', 'discount_pct', 'deleted']

    def _get_subtypes(self, ids):
        from apps.plans_subtype.models import PlansSubtype
        subtypes = PlansSubtype.objects.filter(id__in=ids)
        if len(subtypes) != len(ids):
            found = set(subtypes.values_list('id', flat=True))
            missing = set(ids) - found
            raise serializers.ValidationError(
                {'plans_ids': f'IDs de subtype no encontrados: {sorted(missing)}'}
            )
        return subtypes

    def create(self, validated_data):
        ids = validated_data.pop('plans_ids')
        instance = ComboPlanDiscount.objects.create(**validated_data)
        instance.plans.set(self._get_subtypes(ids))
        return instance

    def update(self, instance, validated_data):
        ids = validated_data.pop('plans_ids', None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if ids is not None:
            instance.plans.set(self._get_subtypes(ids))
        return instance


class PlanDiscountSerializer(serializers.ModelSerializer):
    plans_subtype_name = serializers.CharField(source='plans_subtype.name', read_only=True)

    class Meta:
        model = PlanDiscount
        fields = ['id', 'plans_subtype', 'plans_subtype_name', 'discount_pct', 'deleted']

    def validate_plans_subtype(self, value):
        """Un plan no puede tener dos descuentos activos a la vez. Los soft-deleted
        no cuentan (manager `objects`). Al editar, se excluye el propio registro."""
        qs = PlanDiscount.objects.filter(plans_subtype=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                'Ya existe un descuento activo para este plan.'
            )
        return value


class PlansTypePublicSerializer(serializers.ModelSerializer):
    subtypes = serializers.SerializerMethodField()

    class Meta:
        model = PlansType
        fields = ['id', 'name', 'subtypes']

    def get_subtypes(self, obj):
        from apps.plans_subtype.serializer import PlansSubtypePublicSerializer
        from apps.payment_method.models import PaymentMethod
        qs = obj.subtypes.filter(deleted__isnull=True).prefetch_related(
            Prefetch(
                'payment_methods',
                queryset=PaymentMethod.objects.filter(deleted__isnull=True),
                to_attr='alive_payment_methods',
            )
        )
        return PlansSubtypePublicSerializer(qs, many=True).data


class ComboPlanDiscountPublicSerializer(serializers.ModelSerializer):
    # Devuelve subtypes (no types): el alumno ve el plan concreto que aplica el descuento
    plans = ComboSubtypeSerializer(many=True, read_only=True)

    class Meta:
        model = ComboPlanDiscount
        fields = ['id', 'name', 'plans', 'discount_pct']
