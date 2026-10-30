from django.db import models
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class RecommendationAnalysis(SoftDeleteMixin):
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('users.CustomUser', on_delete=models.SET_NULL, null=True, blank=True)
    window_weeks = models.PositiveSmallIntegerField()
    window_start = models.DateField()
    window_end = models.DateField()
    min_classes = models.PositiveSmallIntegerField()
    high_occupancy_threshold = models.FloatField()
    high_occupancy_ratio = models.FloatField()
    low_occupancy_threshold = models.FloatField()
    low_occupancy_ratio = models.FloatField()
    deleted = models.DateTimeField(null=True, blank=True)

    objects = DeletedManager()
    all_objects = DeletedQuerySet.as_manager()


class Recommendation(SoftDeleteMixin):
    TYPE_CHOICES = [('add', 'add'), ('relocate', 'relocate'), ('reduce', 'reduce')]
    STATE_CHOICES = [('pending', 'pending'), ('accepted', 'accepted'), ('discarded', 'discarded')]

    analysis = models.ForeignKey(RecommendationAnalysis, on_delete=models.CASCADE, related_name='recommendations')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    studio = models.ForeignKey('studios.Studio', on_delete=models.CASCADE)
    room = models.ForeignKey('rooms.Room', on_delete=models.SET_NULL, null=True, blank=True)
    activity_subtype = models.ForeignKey('activity_subtype.ActivitySubType', on_delete=models.SET_NULL, null=True, blank=True)
    weekday = models.PositiveSmallIntegerField()
    start_time = models.TimeField()
    period_start = models.DateField()
    period_end = models.DateField()
    observations_count = models.IntegerField(default=0)
    occupancy_avg = models.FloatField(default=0)
    high_ratio = models.FloatField(default=0)
    low_ratio = models.FloatField(default=0)
    waitlist_count = models.IntegerField(default=0)
    affected_count = models.IntegerField(default=0)
    rules_applied = models.JSONField(default=dict)
    pending_conditions = models.JSONField(default=list)
    proposed_alternative = models.JSONField(null=True, blank=True)
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default='pending')
    decided_by = models.ForeignKey('users.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='decided_recommendations')
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted = models.DateTimeField(null=True, blank=True)

    objects = DeletedManager()
    all_objects = DeletedQuerySet.as_manager()
