from django.db import models
from django.contrib.gis.db import models as gis_models
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.core.models import BaseModel

class Campaign(BaseModel):
    """
    Campaign model representing advertising campaigns created by agencies for their clients
    """
    
    CAMPAIGN_STATUS = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    CAMPAIGN_TYPES = [
        ('brand_awareness', 'Brand Awareness'),
        ('product_launch', 'Product Launch'),
        ('promotional', 'Promotional'),
        ('event', 'Event Marketing'),
        ('seasonal', 'Seasonal Campaign'),
    ]
    
    # Relationships
    agency = models.ForeignKey(
        'agencies.Agency',
        on_delete=models.CASCADE,
        related_name='campaigns'
    )
    client = models.ForeignKey(
        'agencies.AgencyClient',
        on_delete=models.CASCADE,
        related_name='campaigns'
    )
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='created_campaigns'
    )
    
    # Basic Information
    name = models.CharField(max_length=255)
    description = models.TextField()
    campaign_type = models.CharField(max_length=20, choices=CAMPAIGN_TYPES)
    status = models.CharField(max_length=20, choices=CAMPAIGN_STATUS, default='draft')
    
    # Creative Assets
    sticker_design = models.ImageField(upload_to='campaigns/stickers/')
    sticker_preview = models.ImageField(upload_to='campaigns/previews/', blank=True, null=True)
    brand_colors = models.JSONField(default=list)  # List of hex colors
    brand_logo = models.ImageField(upload_to='campaigns/logos/', blank=True, null=True)
    
    # Campaign Details
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    target_audience = models.TextField(blank=True)
    marketing_objectives = models.TextField(blank=True)
    
    # Geographic Targeting
    target_areas = gis_models.MultiPolygonField(blank=True, null=True)
    target_cities = models.JSONField(default=list)  # List of city names
    exclude_areas = gis_models.MultiPolygonField(blank=True, null=True)
    
    # Rider Requirements
    required_riders = models.PositiveIntegerField()
    assigned_riders = models.ManyToManyField(
        'riders.Rider',
        through='CampaignRiderAssignment',
        related_name='campaigns'
    )
    
    # Financial (as per plan specifications)
    platform_rate = models.DecimalField(max_digits=10, decimal_places=2)  # Per rider
    agency_rate = models.DecimalField(max_digits=10, decimal_places=2)  # What agency charges client
    total_budget = models.DecimalField(max_digits=10, decimal_places=2)
    spent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Performance Tracking
    target_impressions = models.PositiveIntegerField(blank=True, null=True)
    actual_impressions = models.PositiveIntegerField(default=0)
    verification_frequency = models.PositiveIntegerField(default=3)  # per day
    
    # Plan-specific performance fields
    total_distance = models.FloatField(default=0)
    total_verifications = models.IntegerField(default=0)
    verification_pass_rate = models.FloatField(default=0)
    
    # Defensive data collection (as per plan)
    performance_score = models.FloatField(default=0)
    market_insights = models.JSONField(default=dict)
    
    # Creative assets (as per plan)
    sticker_certificate = models.FileField(upload_to='certificates/', blank=True, null=True)
    
    # Approval Workflow
    approved_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        related_name='approved_campaigns',
        blank=True,
        null=True
    )
    approved_at = models.DateTimeField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True)
    
    # Metadata
    tags = models.JSONField(default=list)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['agency', 'status']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.client.name}"
    
    @property
    def is_active(self):
        from django.utils import timezone
        now = timezone.now()
        return (
            self.status == 'active' and
            self.start_date <= now <= self.end_date
        )
    
    @property
    def rider_cost_total(self):
        return self.required_riders * self.cost_per_rider
    
    @property
    def agency_revenue(self):
        return (self.total_budget * self.agency_margin) / 100
    
    @property
    def platform_revenue(self):
        return (self.total_budget * self.platform_commission) / 100

class CampaignRiderAssignment(BaseModel):
    """
    Through model for Campaign-Rider relationship with additional data
    """
    
    ASSIGNMENT_STATUS = [
        ('assigned', 'Assigned'),
        ('accepted', 'Accepted'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    rider = models.ForeignKey('riders.Rider', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=ASSIGNMENT_STATUS, default='assigned')
    
    # Assignment Details
    assigned_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='rider_assignments'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    # Performance Tracking
    verification_count = models.PositiveIntegerField(default=0)
    compliance_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    distance_covered = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # km
    
    # Payment
    amount_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('paid', 'Paid'),
            ('failed', 'Failed'),
        ],
        default='pending'
    )
    
    class Meta:
        unique_together = ['campaign', 'rider']
        indexes = [
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['rider', 'status']),
        ]
    
    def __str__(self):
        return f"{self.rider} - {self.campaign.name}"

class CampaignMetrics(BaseModel):
    """Daily aggregated metrics for campaigns"""
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='daily_metrics')
    date = models.DateField()
    
    # Performance Metrics
    active_riders = models.PositiveIntegerField(default=0)
    total_verifications = models.PositiveIntegerField(default=0)
    successful_verifications = models.PositiveIntegerField(default=0)
    estimated_impressions = models.PositiveIntegerField(default=0)
    distance_covered = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # km
    
    # Geographic Coverage
    areas_covered = models.JSONField(default=list)  # List of area names/coordinates
    unique_locations = models.PositiveIntegerField(default=0)
    
    # Compliance
    compliance_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    class Meta:
        unique_together = ['campaign', 'date']
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.campaign.name} - {self.date}"

class CampaignReport(BaseModel):
    """Generated reports for campaigns (for agencies to share with clients)"""
    
    REPORT_TYPES = [
        ('daily', 'Daily Report'),
        ('weekly', 'Weekly Report'),
        ('monthly', 'Monthly Report'),
        ('final', 'Final Report'),
        ('custom', 'Custom Report'),
    ]
    
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='reports')
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    
    # Report Period
    start_date = models.DateField()
    end_date = models.DateField()
    
    # Generated Content
    title = models.CharField(max_length=255)
    summary = models.TextField()
    insights = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    
    # Data
    metrics_data = models.JSONField(default=dict)
    charts_data = models.JSONField(default=dict)
    
    # File Outputs
    pdf_report = models.FileField(upload_to='reports/pdf/', blank=True, null=True)
    excel_report = models.FileField(upload_to='reports/excel/', blank=True, null=True)
    
    # White-label Settings
    use_agency_branding = models.BooleanField(default=True)
    include_platform_branding = models.BooleanField(default=False)
    
    # Status
    is_generated = models.BooleanField(default=False)
    generated_at = models.DateTimeField(blank=True, null=True)
    generated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        blank=True,
        null=True
    )
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.report_type.title()} Report - {self.campaign.name}"