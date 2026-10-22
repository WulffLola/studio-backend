
from rest_framework import viewsets
from .serializer import PaymentMethodSerializer
from .models import PaymentMethod
from rest_framework import viewsets, status
from rest_framework.response import Response
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper

class PaymentMethodViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentMethodSerializer
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]

    def get_queryset(self):
        return PaymentMethod.all_objects.for_user(self.request.user).select_related(
            'plans_subtype__activity_subtype'
        )

    def create(self, request, *args, **kwargs):
        plans_subtype = request.data.get('plans_subtype')
        method = request.data.get('method')

        # Bloquear combinación duplicada (plans_subtype, method) case-insensitive.
        if PaymentMethod.objects.filter(
            plans_subtype=plans_subtype, method__iexact=method, deleted__isnull=True
        ).exists():
            return Response(
                {"detail": "This combination of plan and payment method already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().create(request, *args, **kwargs)
