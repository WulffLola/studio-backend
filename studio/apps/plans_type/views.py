from django.db.models import Prefetch
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from decimal import Decimal, InvalidOperation
from .serializer import (
    PlansTypeSerializer,
    ComboPlanDiscountSerializer,
    ComboPlanDiscountPublicSerializer,
    PlanDiscountSerializer,
)
from .models import PlansType, ComboPlanDiscount, PlanDiscount
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper, StudentReadMixin
from apps.plans_subtype.models import PlansSubtype
from apps.plans_subtype.serializer import PlansSubtypePublicSerializer
from apps.payment_method.models import PaymentMethod


def _discounted_amount(amount, disc):
    """Aplica el descuento combo al precio de un PaymentMethod.

    `amount` es un CharField (texto libre); si no es un número válido
    (vacío, None o no numérico) devuelve None en vez de romper.
    Retorna el precio con descuento como string con 2 decimales.
    """
    if amount in (None, ''):
        return None
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return str(round(value * (1 - disc / 100), 2))


class PlansTypeViewSet(StudentReadMixin, viewsets.ModelViewSet):
    queryset = PlansType.objects.all()
    serializer_class = PlansTypeSerializer
    write_permission = IsAdministrador | IsConsultor | IsSuper

    def get_queryset(self):
        return PlansType.all_objects.for_user(self.request.user)


class ComboPlanDiscountViewSet(StudentReadMixin, viewsets.ModelViewSet):
    serializer_class = ComboPlanDiscountSerializer
    write_permission = IsAdministrador | IsSuper

    def get_queryset(self):
        return ComboPlanDiscount.all_objects.for_user(self.request.user)


class PlanDiscountViewSet(viewsets.ModelViewSet):
    serializer_class = PlanDiscountSerializer
    permission_classes = [IsAdministrador | IsSuper]

    def get_queryset(self):
        return PlanDiscount.all_objects.for_user(self.request.user)


class PricesViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET /prices/
    Devuelve los planes concretos (PlansSubtype) con precio, tipo padre
    y subactividades.

    GET /prices/combo-preview/?plans=1,2,3
    Devuelve los planes solicitados con el precio final aplicando combos.
    Si algún combo aplica, lo informa en 'applied_combos'.
    """
    permission_classes = [AllowAny]
    serializer_class = PlansSubtypePublicSerializer

    def get_queryset(self):
        return PlansSubtype.objects.select_related(
            'plan_type',
            'activity_subtype__activity_type',
        ).prefetch_related(
            Prefetch(
                'payment_methods',
                queryset=PaymentMethod.objects.filter(deleted__isnull=True),
                to_attr='alive_payment_methods',
            )
        ).filter(deleted__isnull=True)

    @action(detail=False, methods=['get'], url_path='combo-preview')
    def combo_preview(self, request):
        plans_param = request.query_params.get('plans', '')
        if not plans_param:
            return Response(
                {"detail": "Parámetro 'plans' requerido. Ej: ?plans=1,2,3"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            subtype_ids = [int(i) for i in plans_param.split(',') if i.strip()]
        except ValueError:
            return Response(
                {"detail": "El parámetro 'plans' debe ser una lista de IDs enteros separados por coma."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subtypes = PlansSubtype.objects.select_related(
            'plan_type', 'activity_subtype__activity_type'
        ).prefetch_related(
            Prefetch(
                'payment_methods',
                queryset=PaymentMethod.objects.filter(deleted__isnull=True),
                to_attr='alive_payment_methods',
            )
        ).filter(id__in=subtype_ids, deleted__isnull=True)

        found_ids = set(subtypes.values_list('id', flat=True))
        missing = set(subtype_ids) - found_ids
        if missing:
            return Response(
                {"detail": f"Plans no encontrados: {sorted(missing)}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        from apps.payments.services import find_applicable_combos, find_applicable_plan_discounts
        applicable_combos = find_applicable_combos(subtype_ids)

        # Descuento máximo por subtype: combos y descuentos por plan, gana el mayor.
        max_discount = {}
        for combo in applicable_combos:
            for sid in combo['matching_subtype_ids']:
                if combo['discount_pct'] > max_discount.get(sid, Decimal('0')):
                    max_discount[sid] = combo['discount_pct']
        for sid, pct in find_applicable_plan_discounts(subtype_ids).items():
            if pct > max_discount.get(sid, Decimal('0')):
                max_discount[sid] = pct

        plans_data = []
        for ps in subtypes:
            disc = max_discount.get(ps.id, Decimal('0'))
            data = PlansSubtypePublicSerializer(ps).data
            # Fuente de verdad de precios = PaymentMethod: el descuento
            # se aplica por método de pago (final_amount).
            for pm in data['payment_methods']:
                pm['final_amount'] = _discounted_amount(pm['amount'], disc)
            plans_data.append({
                **data,
                'discount_pct': disc,
            })

        # applied_combos: solo combos con match EXACTO (todos los planes pedidos,
        # ni de más ni de menos). El descuento por plan de arriba sigue usando el
        # match parcial/subset (no cambia).
        requested = set(subtype_ids)
        exact_combos = [
            c for c in applicable_combos
            if len(c['matching_subtype_ids']) == len(requested)
        ]

        return Response({
            'plans': plans_data,
            'applied_combos': exact_combos,
        }, status=status.HTTP_200_OK)


class AvailablePlansViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET /available-plans/
    Devuelve los planes concretos activos (PlansSubtype) con subactividades,
    más los combos de descuento vigentes.
    """
    permission_classes = [AllowAny]
    queryset = PlansSubtype.objects.none()  # requerido por el router

    def list(self, request, *args, **kwargs):
        plans = PlansSubtype.objects.select_related(
            'plans_type',
            'activity_subtype__activity_type',
        ).prefetch_related(
            Prefetch(
                'payment_methods',
                queryset=PaymentMethod.objects.filter(deleted__isnull=True),
                to_attr='alive_payment_methods',
            )
        ).filter(deleted__isnull=True)

        combos = ComboPlanDiscount.objects.prefetch_related(
            'plans__plans_type'
        ).filter(deleted__isnull=True)

        return Response({
            'plans': PlansSubtypePublicSerializer(plans, many=True).data,
            'combos': ComboPlanDiscountPublicSerializer(combos, many=True).data,
        })
