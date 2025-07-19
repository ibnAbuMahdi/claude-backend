from django.db import models
from django.contrib.gis.db import models as gis_models
from apps.core.models import BaseModel

class VerificationRequest(BaseModel):
    """Computer vision verification requests from riders"""
    
    VERIFICATION_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('manual_review', 'Manual Review'),
    ]
    
    rider = models.ForeignKey('riders.Rider', on_delete=models.CASCADE)
    campaign = models.ForeignKey('campaigns.Campaign', on_delete=models.CASCADE)
    
    # Image Data
    image = models.ImageField(upload_to='verifications/')
    image_metadata = models.JSONField(default=dict)
    
    # Location Data
    location = gis_models.PointField()
    accuracy = models.FloatField()
    timestamp = models.DateTimeField()
    
    # Verification Results
    status = models.CharField(max_length=20, choices=VERIFICATION_STATUS, default='pending')
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ai_analysis = models.JSONField(default=dict)
    
    def __str__(self):
        return f"{self.rider.rider_id} - {self.campaign.name}"