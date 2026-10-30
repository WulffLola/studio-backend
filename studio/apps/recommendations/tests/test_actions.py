import pytest
from datetime import date, time
from django.urls import reverse


def _make(studio):
    from apps.recommendations.models import RecommendationAnalysis, Recommendation
    a = RecommendationAnalysis.objects.create(
        window_weeks=8, window_start=date(2026, 8, 1), window_end=date(2026, 9, 26),
        min_classes=8, high_occupancy_threshold=0.8, high_occupancy_ratio=0.6,
        low_occupancy_threshold=0.5, low_occupancy_ratio=0.6)
    return Recommendation.objects.create(
        analysis=a, type='add', studio=studio, weekday=0,
        start_time=time(10, 0), period_start=a.window_start, period_end=a.window_end)


@pytest.mark.django_db
def test_accept_sets_decision(admin_client, admin_user, studio):
    r = _make(studio)
    resp = admin_client.post(reverse('recommendations-accept', args=[r.id]))
    assert resp.status_code == 200
    r.refresh_from_db()
    assert r.state == 'accepted'
    assert r.decided_by_id == admin_user.id and r.decided_at is not None
    # segunda decisión -> 409
    resp2 = admin_client.post(reverse('recommendations-discard', args=[r.id]))
    assert resp2.status_code == 409
    r.refresh_from_db()
    assert r.state == 'accepted'


@pytest.mark.django_db
def test_discard_sets_decision(admin_client, admin_user, studio):
    r = _make(studio)
    resp = admin_client.post(reverse('recommendations-discard', args=[r.id]))
    assert resp.status_code == 200
    r.refresh_from_db()
    assert r.state == 'discarded'
    assert r.decided_by_id == admin_user.id and r.decided_at is not None
