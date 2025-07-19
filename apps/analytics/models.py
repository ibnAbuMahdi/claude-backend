from django.db import models
from apps.core.models import BaseModel

class AnalyticsEvent(BaseModel):
    """Track platform events for analytics"""
    
    EVENT_TYPES = [
        ('campaign_created', 'Campaign Created'),
        ('rider_assigned', 'Rider Assigned'),
        ('verification_completed', 'Verification Completed'),
        ('payment_processed', 'Payment Processed'),
    ]
    
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, null=True, blank=True)
    agency = models.ForeignKey('agencies.Agency', on_delete=models.CASCADE, null=True, blank=True)
    
    # Event Data
    event_data = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.event_type} - {self.timestamp}"