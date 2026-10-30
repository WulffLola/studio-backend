from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from apps.user_type.permisos import IsAdministrador, IsSuper
from .models import RecommendationAnalysis, Recommendation
from .serializer import (RecommendationSerializer, RecommendationAnalysisSerializer,
                         AnalyzeParamsSerializer)
from . import services


class RecommendationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RecommendationSerializer
    permission_classes = [IsAdministrador | IsSuper]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['state', 'type', 'studio', 'analysis']

    def get_queryset(self):
        return Recommendation.objects.all().order_by('-created_at')

    @action(detail=False, methods=['post'])
    def analyze(self, request):
        params_ser = AnalyzeParamsSerializer(data=request.data)
        params_ser.is_valid(raise_exception=True)
        p = services.Params(**params_ser.validated_data)
        user = request.user if request.user.is_authenticated else None
        with transaction.atomic():
            analysis = services.run_analysis(p, user=user)
        data = RecommendationAnalysisSerializer(analysis).data
        return Response({"summary": analysis.run_summary, **data}, status=status.HTTP_201_CREATED)

    def _decide(self, request, pk, new_state):
        rec = self.get_object()
        if rec.state != 'pending':
            return Response({"detail": "La recomendación ya fue decidida."},
                            status=status.HTTP_409_CONFLICT)
        rec.state = new_state
        rec.decided_by = request.user if request.user.is_authenticated else None
        rec.decided_at = timezone.now()
        rec.save(update_fields=['state', 'decided_by', 'decided_at'])
        return Response(RecommendationSerializer(rec).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        return self._decide(request, pk, 'accepted')

    @action(detail=True, methods=['post'])
    def discard(self, request, pk=None):
        return self._decide(request, pk, 'discarded')


class RecommendationAnalysisViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RecommendationAnalysisSerializer
    permission_classes = [IsAdministrador | IsSuper]

    def get_queryset(self):
        return RecommendationAnalysis.objects.all().prefetch_related('recommendations').order_by('-created_at')
