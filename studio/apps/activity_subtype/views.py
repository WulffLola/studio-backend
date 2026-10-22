from rest_framework import viewsets
from django.db.models import Prefetch
from .serializer import ActivitySubTypeSerializer
from .models import ActivitySubType
from apps.plans_subtype.models import PlansSubtype
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper, StudentReadMixin

class ActivitySubTypeViewSet(StudentReadMixin, viewsets.ModelViewSet):
    queryset = ActivitySubType.objects.all()
    serializer_class = ActivitySubTypeSerializer
    write_permission = IsAdministrador | IsConsultor | IsSuper

    def get_queryset(self):
        return ActivitySubType.all_objects.for_user(self.request.user).prefetch_related(
            Prefetch(
                'plans_subtypes',
                queryset=PlansSubtype.objects.filter(deleted__isnull=True).select_related('plan_type'),
                to_attr='alive_plans_subtypes',
            )
        )
