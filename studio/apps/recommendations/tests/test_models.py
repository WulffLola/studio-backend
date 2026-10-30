import pytest
from django.utils import timezone
from datetime import date

@pytest.mark.django_db
def test_create_analysis_and_recommendation(studio):
    from apps.recommendations.models import RecommendationAnalysis, Recommendation
    a = RecommendationAnalysis.objects.create(
        window_weeks=8, window_start=date(2026, 8, 1), window_end=date(2026, 9, 26),
        min_classes=8, high_occupancy_threshold=0.8, high_occupancy_ratio=0.6,
        low_occupancy_threshold=0.5, low_occupancy_ratio=0.6,
    )
    r = Recommendation.objects.create(
        analysis=a, type='add', studio=studio, weekday=0, start_time='10:00',
        period_start=a.window_start, period_end=a.window_end,
        observations_count=10, occupancy_avg=0.9, high_ratio=0.8, low_ratio=0.0,
        waitlist_count=3, affected_count=0,
    )
    assert r.state == 'pending'
    assert r.decided_by is None and r.decided_at is None
    assert a.recommendations.count() == 1
