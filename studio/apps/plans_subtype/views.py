from django.db.models import Prefetch
from rest_framework import viewsets
from .serializer import PlansSubtypeSerializer
from .models import PlansSubtype
from apps.payment_method.models import PaymentMethod
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper, StudentReadMixin

class PlansSubtypeViewSet(StudentReadMixin, viewsets.ModelViewSet):
    queryset = PlansSubtype.objects.all()
    serializer_class = PlansSubtypeSerializer
    write_permission = IsAdministrador | IsConsultor | IsSuper

    def get_queryset(self):
        return PlansSubtype.all_objects.for_user(self.request.user).prefetch_related(
            Prefetch(
                'payment_methods',
                queryset=PaymentMethod.objects.filter(deleted__isnull=True),
                to_attr='alive_payment_methods',
            )
        )
