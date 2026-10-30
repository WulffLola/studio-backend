from rest_framework import serializers
from .models import RecommendationAnalysis, Recommendation


class RecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recommendation
        fields = '__all__'
        read_only_fields = ['state', 'decided_by', 'decided_at', 'analysis', 'created_at']


class RecommendationAnalysisSerializer(serializers.ModelSerializer):
    recommendations = RecommendationSerializer(many=True, read_only=True)

    class Meta:
        model = RecommendationAnalysis
        fields = '__all__'


class AnalyzeParamsSerializer(serializers.Serializer):
    window_weeks = serializers.IntegerField(required=False, default=8, min_value=8, max_value=12)
    min_classes = serializers.IntegerField(required=False, default=8, min_value=1)
    high_occupancy_threshold = serializers.FloatField(required=False, default=0.8, min_value=0.0, max_value=1.0)
    high_occupancy_ratio = serializers.FloatField(required=False, default=0.6, min_value=0.0, max_value=1.0)
    low_occupancy_threshold = serializers.FloatField(required=False, default=0.5, min_value=0.0, max_value=1.0)
    low_occupancy_ratio = serializers.FloatField(required=False, default=0.6, min_value=0.0, max_value=1.0)

    @staticmethod
    def _gt_zero(value):
        if value <= 0:
            raise serializers.ValidationError('Debe ser mayor que 0.')
        return value

    def validate_high_occupancy_threshold(self, value):
        return self._gt_zero(value)

    def validate_high_occupancy_ratio(self, value):
        return self._gt_zero(value)

    def validate_low_occupancy_ratio(self, value):
        return self._gt_zero(value)

    def validate_low_occupancy_threshold(self, value):
        if value >= 1:
            raise serializers.ValidationError('Debe ser menor que 1.')
        return value
