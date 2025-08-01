from django.db import models
from django.contrib.gis.db import models as gis_models
from django.utils import timezone
from datetime import timedelta
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
    
    VERIFICATION_TYPES = [
        ('random', 'Random Verification'),
        ('geofence_join', 'Geofence Join Verification'),
        ('manual', 'Manual Verification'),
    ]
    
    rider = models.ForeignKey('riders.Rider', on_delete=models.CASCADE)
    campaign = models.ForeignKey('campaigns.Campaign', on_delete=models.CASCADE)
    
    # New fields for geofence joining
    geofence = models.ForeignKey(
        'campaigns.CampaignGeofence', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="Geofence being joined (for geofence_join type)"
    )
    verification_type = models.CharField(
        max_length=20,
        choices=VERIFICATION_TYPES,
        default='random',
        help_text="Type of verification request"
    )
    
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
    
    # Cooldown tracking
    attempted_at = models.DateTimeField(auto_now_add=True)
    can_retry_after = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        indexes = [
            models.Index(fields=['rider', 'verification_type', 'attempted_at']),
            models.Index(fields=['can_retry_after']),
            models.Index(fields=['geofence', 'status']),
            models.Index(fields=['verification_type', 'status']),
        ]
    
    def __str__(self):
        geofence_info = f" - {self.geofence.name}" if self.geofence else ""
        return f"{self.rider.rider_id} - {self.campaign.name}{geofence_info} ({self.verification_type})"


class VerificationCooldown(BaseModel):
    """Track verification attempt cooldowns per rider"""
    
    COOLDOWN_PERIODS = {
        'geofence_join': 60,  # 1 minute
        'random': 300,        # 5 minutes
        'manual': 0,          # No cooldown
    }
    
    rider = models.ForeignKey('riders.Rider', on_delete=models.CASCADE)
    verification_type = models.CharField(max_length=20, choices=VerificationRequest.VERIFICATION_TYPES)
    last_attempt = models.DateTimeField()
    cooldown_until = models.DateTimeField()
    attempt_count = models.PositiveIntegerField(default=1)
    
    class Meta:
        unique_together = ['rider', 'verification_type']
        indexes = [
            models.Index(fields=['rider', 'verification_type']),
            models.Index(fields=['cooldown_until']),
        ]
    
    def __str__(self):
        return f"{self.rider.rider_id} - {self.verification_type} cooldown until {self.cooldown_until}"
    
    @property
    def is_active(self):
        """Check if cooldown is still active"""
        return timezone.now() < self.cooldown_until
    
    @property
    def remaining_seconds(self):
        """Get remaining cooldown time in seconds"""
        if self.is_active:
            return int((self.cooldown_until - timezone.now()).total_seconds())
        return 0
    
    @classmethod
    def check_cooldown(cls, rider, verification_type):
        """
        Check if rider is in cooldown period for verification type
        Returns: (can_verify: bool, cooldown_remaining: int)
        """
        try:
            cooldown = cls.objects.get(
                rider=rider,
                verification_type=verification_type
            )
            
            if cooldown.is_active:
                return False, cooldown.remaining_seconds
            else:
                # Cooldown expired, can proceed
                return True, 0
                
        except cls.DoesNotExist:
            # No cooldown record, can proceed
            return True, 0
    
    @classmethod
    def set_cooldown(cls, rider, verification_type, additional_seconds=0):
        """Set cooldown after verification attempt"""
        cooldown_seconds = cls.COOLDOWN_PERIODS.get(verification_type, 60)
        cooldown_seconds += additional_seconds
        
        cooldown_until = timezone.now() + timedelta(seconds=cooldown_seconds)
        
        # First check if record exists to determine attempt count logic
        try:
            existing_cooldown = cls.objects.get(
                rider=rider,
                verification_type=verification_type
            )
            # Update existing record
            existing_cooldown.last_attempt = timezone.now()
            existing_cooldown.cooldown_until = cooldown_until
            existing_cooldown.attempt_count = models.F('attempt_count') + 1
            existing_cooldown.save(update_fields=['last_attempt', 'cooldown_until', 'attempt_count'])
            
            # Refresh to get the updated attempt_count value
            existing_cooldown.refresh_from_db()
            return existing_cooldown
            
        except cls.DoesNotExist:
            # Create new record
            cooldown = cls.objects.create(
                rider=rider,
                verification_type=verification_type,
                last_attempt=timezone.now(),
                cooldown_until=cooldown_until,
                attempt_count=1
            )
            return cooldown