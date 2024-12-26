from django.db import models
from django.utils import timezone

class Branch(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Camera(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='cameras')
    stream_url = models.URLField(max_length=500)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.branch.name} - Camera {self.id}"

class PersonCount(models.Model):
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name='counts')
    count = models.IntegerField(default=0)  # Current count
    total_count = models.IntegerField(default=0)  # Total unique count
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.camera} - Current: {self.count}, Total: {self.total_count} at {self.timestamp}"

class DailyStats(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='daily_stats')
    date = models.DateField()
    total_count = models.IntegerField(default=0)
    peak_hour = models.IntegerField(null=True)
    peak_count = models.IntegerField(default=0)
    unique_visitors = models.IntegerField(default=0)  # Added for tracking unique visitors

    class Meta:
        unique_together = ('branch', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.branch.name} - {self.date} - Total: {self.total_count}, Unique: {self.unique_visitors}"