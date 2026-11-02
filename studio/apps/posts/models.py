from django.db import models
from django.utils import timezone
from utils import SoftDeleteManager, SoftDeleteQuerySet


class Post(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_DELETED = 'deleted'

    STATUS_CHOICES = (
        (STATUS_DRAFT, 'Draft'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PAUSED, 'Paused'),
        (STATUS_DELETED, 'Deleted'),
    )

    title = models.CharField(max_length=200)
    caption = models.TextField(blank=True, default='')
    image = models.ImageField(upload_to='posts/images/', null=True, blank=True)
    video = models.FileField(upload_to='posts/videos/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        ordering = ['-published_at', '-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Auto-fill published_at the first time status becomes active
        if self.status == self.STATUS_ACTIVE and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        self.status = self.STATUS_DELETED
        self.deleted_at = timezone.now()
        self.save(update_fields=['status', 'deleted_at'])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.deleted_at = None
        self.status = self.STATUS_DRAFT
        self.save(update_fields=['status', 'deleted_at'])
