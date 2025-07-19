from django.db import models
from django.contrib.gis.db import models as gis_models
from django.core.validators import MinValueValidator, MaxValueValidator
from phonenumber_field.modelfields import PhoneNumberField
from apps.core.models import BaseModel

class Rider(BaseModel):
    """
    Rider model representing tricycle operators who display campaign stickers
    """
    
    RIDER_STATUS = [
        ('pending', 'Pending Verification'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
        ('banned', 'Banned'),
    ]
    
    VERIFICATION_STATUS = [
        ('unverified', 'Unverified'),
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    
    # Personal Information
    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='rider_profile'
    )
    rider_id = models.CharField(max_length=20, unique=True)  # STK-R-XXXXX format
    date_of_birth = models.DateField()
    gender = models.CharField(
        max_length=10,
        choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')]
    )
    
    # Contact Information
    phone_number = PhoneNumberField()
    emergency_contact_name = models.CharField(max_length=100)
    emergency_contact_phone = PhoneNumberField()
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    
    # Verification Documents
    nin = models.CharField(max_length=11, blank=True)  # National ID
    drivers_license = models.CharField(max_length=20, blank=True)
    passport_photo = models.ImageField(upload_to='riders/photos/')
    id_document = models.ImageField(upload_to='riders/documents/')
    
    # Tricycle Information
    tricycle_registration = models.CharField(max_length=20)
    tricycle_model = models.CharField(max_length=100, blank=True)
    tricycle_year = models.PositiveIntegerField(blank=True, null=True)
    tricycle_color = models.CharField(max_length=50, blank=True)
    tricycle_photos = models.JSONField(default=list)  # List of image URLs
    
    # Fleet Relationship
    fleet_owner = models.ForeignKey(
        'fleets.FleetOwner',
        on_delete=models.CASCADE,
        related_name='riders',
        blank=True,
        null=True
    )
    
    # Status and Verification
    status = models.CharField(max_length=20, choices=RIDER_STATUS, default='pending')
    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUS,
        default='unverified'
    )
    verified_at = models.DateTimeField(blank=True, null=True)
    verified_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        related_name='verified_riders',
        blank=True,
        null=True
    )
    
    # Performance Metrics
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=5.00,
        validators=[MinValueValidator(1.0), MaxValueValidator(5.0)]
    )
    compliance_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    total_campaigns = models.PositiveIntegerField(default=0)
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pending_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Plan-specific proprietary scoring
    reliability_score = models.FloatField(default=100.0)
    route_efficiency_score = models.FloatField(default=0.0)
    verification_compliance_score = models.FloatField(default=100.0)
    
    # Anti-gaming features (as per plan)
    suspicious_activity_count = models.IntegerField(default=0)
    last_verification_request = models.DateTimeField(null=True, blank=True)
    
    # Availability
    is_available = models.BooleanField(default=True)
    preferred_work_hours = models.JSONField(default=dict)  # Schedule preferences
    max_concurrent_campaigns = models.PositiveIntegerField(default=1)
    
    # Banking Information
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=100, blank=True)
    bvn = models.CharField(max_length=11, blank=True)
    
    # Location and Route
    current_location = gis_models.PointField(blank=True, null=True)
    usual_routes = gis_models.MultiLineStringField(blank=True, null=True)
    operating_areas = models.JSONField(default=list)  # List of area names
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'verification_status']),
            models.Index(fields=['fleet_owner', 'status']),
            models.Index(fields=['rider_id']),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name()} ({self.rider_id})"
    
    def save(self, *args, **kwargs):
        if not self.rider_id:
            # Generate unique rider ID
            import random
            self.rider_id = f"STK-R-{random.randint(10000, 99999)}"
        super().save(*args, **kwargs)
    
    @property
    def active_campaigns(self):
        from django.utils import timezone
        now = timezone.now()
        return self.campaigns.filter(
            status='active',
            start_date__lte=now,
            end_date__gte=now
        )
    
    @property
    def current_campaign_count(self):
        return self.active_campaigns.count()
    
    @property
    def can_accept_campaign(self):
        return (
            self.status == 'active' and
            self.is_available and
            self.current_campaign_count < self.max_concurrent_campaigns
        )

class RiderLocation(BaseModel):
    """Track rider locations for route optimization and verification"""
    rider = models.ForeignKey(Rider, on_delete=models.CASCADE, related_name='location_history')
    location = gis_models.PointField()
    accuracy = models.FloatField()  # GPS accuracy in meters
    speed = models.FloatField(blank=True, null=True)  # km/h
    heading = models.FloatField(blank=True, null=True)  # degrees
    altitude = models.FloatField(blank=True, null=True)  # meters
    timestamp = models.DateTimeField()
    
    # Context
    is_working = models.BooleanField(default=True)
    current_campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.SET_NULL,
        blank=True,
        null=True
    )
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['rider', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        return f"{self.rider.rider_id} - {self.timestamp}"

class RiderPerformance(BaseModel):
    """Weekly/monthly performance summary for riders"""
    rider = models.ForeignKey(Rider, on_delete=models.CASCADE, related_name='performance_history')
    period_start = models.DateField()
    period_end = models.DateField()
    period_type = models.CharField(
        max_length=10,
        choices=[('weekly', 'Weekly'), ('monthly', 'Monthly')]
    )
    
    # Campaign Metrics
    campaigns_completed = models.PositiveIntegerField(default=0)
    total_verifications = models.PositiveIntegerField(default=0)
    successful_verifications = models.PositiveIntegerField(default=0)
    verification_success_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.00
    )
    
    # Distance and Coverage
    total_distance = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # km
    unique_areas_visited = models.PositiveIntegerField(default=0)
    average_daily_distance = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    
    # Earnings
    total_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bonus_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Compliance
    compliance_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.00
    )
    violations = models.PositiveIntegerField(default=0)
    
    class Meta:
        unique_together = ['rider', 'period_start', 'period_type']
        ordering = ['-period_end']
    
    def __str__(self):
        return f"{self.rider.rider_id} - {self.period_type} {self.period_end}"

class RiderDevice(BaseModel):
    """Track rider mobile devices for app usage and security"""
    rider = models.ForeignKey(Rider, on_delete=models.CASCADE, related_name='devices')
    
    # Device Information
    device_id = models.CharField(max_length=255, unique=True)
    device_name = models.CharField(max_length=100)
    platform = models.CharField(
        max_length=20,
        choices=[('android', 'Android'), ('ios', 'iOS')]
    )
    os_version = models.CharField(max_length=50)
    app_version = models.CharField(max_length=20)
    
    # Security
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(blank=True, null=True)
    fcm_token = models.TextField(blank=True)  # For push notifications
    
    # Settings
    notifications_enabled = models.BooleanField(default=True)
    location_sharing_enabled = models.BooleanField(default=True)
    preferred_language = models.CharField(max_length=10, default='en')
    
    class Meta:
        ordering = ['-last_login']
    
    def __str__(self):
        return f"{self.rider.rider_id} - {self.device_name}"

class RiderPayment(BaseModel):
    """Track payments made to riders"""
    
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_TYPE = [
        ('campaign', 'Campaign Payment'),
        ('bonus', 'Performance Bonus'),
        ('referral', 'Referral Bonus'),
        ('correction', 'Payment Correction'),
    ]
    
    rider = models.ForeignKey(Rider, on_delete=models.CASCADE, related_name='payments')
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE)
    
    # Amount Details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    
    # Payment Details
    reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    payment_method = models.CharField(max_length=50, blank=True)
    external_reference = models.CharField(max_length=100, blank=True)
    
    # Related Campaign (if applicable)
    campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.SET_NULL,
        blank=True,
        null=True
    )
    
    # Processing
    processed_at = models.DateTimeField(blank=True, null=True)
    processed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        blank=True,
        null=True
    )
    
    # Failure Information
    failure_reason = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['rider', 'status']),
            models.Index(fields=['reference']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"Payment {self.reference} - {self.rider.rider_id}"
