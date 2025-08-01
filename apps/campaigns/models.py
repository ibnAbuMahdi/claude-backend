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
    
    # Geographic Targeting (Legacy - for backward compatibility)
    target_areas = gis_models.MultiPolygonField(blank=True, null=True)
    target_cities = models.JSONField(default=list)  # List of city names
    exclude_areas = gis_models.MultiPolygonField(blank=True, null=True)
    
    # Rider Requirements (Now calculated from geofences)
    required_riders = models.PositiveIntegerField(help_text="Total required riders across all geofences")
    assigned_riders = models.ManyToManyField(
        'riders.Rider',
        through='CampaignRiderAssignment',
        related_name='campaigns'
    )
    
    # Financial (Legacy - now per-geofence, these are totals)
    platform_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text="Average rate across geofences")
    agency_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text="Average agency rate")
    total_budget = models.DecimalField(max_digits=10, decimal_places=2, help_text="Sum of all geofence budgets")
    spent = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Total spent across all geofences")
    
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
    
    # Geofence-related methods
    def update_totals_from_geofences(self):
        """Update campaign totals based on geofence data"""
        geofences = self.geofences.all()
        if geofences:
            self.total_budget = sum(g.budget for g in geofences)
            self.spent = sum(g.spent for g in geofences)
            self.required_riders = sum(g.max_riders for g in geofences)
            
            # Calculate average rates
            total_geofences = geofences.count()
            if total_geofences > 0:
                avg_platform_rate = sum(g.rate_per_km or g.rate_per_hour or g.fixed_daily_rate for g in geofences) / total_geofences
                self.platform_rate = avg_platform_rate
            
            self.save(update_fields=['total_budget', 'spent', 'required_riders', 'platform_rate'])
    
    def get_active_geofences(self):
        """Get all currently active geofences"""
        from django.utils import timezone
        now = timezone.now()
        return self.geofences.filter(
            status='active',
            start_date__lte=now,
            end_date__gte=now
        )
    
    def get_available_geofences(self):
        """Get geofences that can still accept riders"""
        return self.get_active_geofences().filter(
            current_riders__lt=models.F('max_riders')
        )
    
    def get_total_available_slots(self):
        """Get total available rider slots across all geofences"""
        available_geofences = self.get_available_geofences()
        total_slots = 0
        for geofence in available_geofences:
            total_slots += geofence.available_slots
        return total_slots
    
    def assign_rider_to_best_geofence(self, rider):
        """
        Assign rider to the best available geofence based on priority and availability
        Returns the CampaignGeofenceAssignment if successful, None otherwise
        """
        available_geofences = self.get_available_geofences().order_by(
            '-is_high_priority', 'priority', 'current_riders'
        )
        
        for geofence in available_geofences:
            if geofence.can_assign_rider():
                # Create campaign rider assignment if it doesn't exist
                campaign_assignment, created = CampaignRiderAssignment.objects.get_or_create(
                    campaign=self,
                    rider=rider,
                    defaults={'assigned_by': getattr(self, '_assigned_by', None)}
                )
                
                # Create geofence assignment
                geofence_assignment = CampaignGeofenceAssignment.objects.create(
                    campaign_geofence=geofence,
                    rider=rider,
                    campaign_rider_assignment=campaign_assignment
                )
                
                # Update counts
                geofence.current_riders += 1
                geofence.save(update_fields=['current_riders'])
                
                return geofence_assignment
        
        return None

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


class CampaignGeofence(BaseModel):
    """
    Individual geofence within a campaign with its own budget, duration, rates, and rider limits
    """
    
    GEOFENCE_STATUS = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    RATE_TYPE_CHOICES = [
        ('per_km', 'Per Kilometer'),
        ('per_hour', 'Per Hour'),
        ('fixed_daily', 'Fixed Daily Rate'),
        ('hybrid', 'Hybrid (KM + Time)'),
    ]
    
    # Relationships
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='geofences'
    )
    
    # Basic Information
    name = models.CharField(max_length=255, help_text="Name of this geofence area")
    description = models.TextField(blank=True, help_text="Description of this specific area")
    priority = models.PositiveIntegerField(default=1, help_text="Priority order for rider assignment")
    
    # Geographic Data
    geofence_data = gis_models.PolygonField(help_text="Actual geofence polygon")
    center_latitude = models.DecimalField(max_digits=10, decimal_places=7)
    center_longitude = models.DecimalField(max_digits=10, decimal_places=7)
    radius_meters = models.PositiveIntegerField(help_text="Radius in meters for circular geofences")
    
    # Individual Budget & Financial Settings
    budget = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Budget allocated specifically for this geofence"
    )
    spent = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Amount spent in this geofence"
    )
    
    # Rate Settings per Geofence
    rate_type = models.CharField(max_length=20, choices=RATE_TYPE_CHOICES, default='per_km')
    rate_per_km = models.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        default=0,
        help_text="Rate paid per kilometer in this geofence"
    )
    rate_per_hour = models.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        default=0,
        help_text="Rate paid per hour in this geofence"
    )
    fixed_daily_rate = models.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        default=0,
        help_text="Fixed daily rate for this geofence"
    )
    
    # Duration Settings
    start_date = models.DateTimeField(help_text="When this geofence becomes active")
    end_date = models.DateTimeField(help_text="When this geofence expires")
    
    # Rider Limits
    max_riders = models.PositiveIntegerField(help_text="Maximum riders allowed in this geofence")
    current_riders = models.PositiveIntegerField(default=0, help_text="Currently assigned riders")
    min_riders = models.PositiveIntegerField(default=1, help_text="Minimum riders needed for this geofence")
    
    # Performance Settings
    target_coverage_hours = models.PositiveIntegerField(
        default=8, 
        help_text="Target hours of coverage per day"
    )
    verification_frequency = models.PositiveIntegerField(
        default=3, 
        help_text="Number of verifications required per day per rider"
    )
    
    # Status and Control
    status = models.CharField(max_length=20, choices=GEOFENCE_STATUS, default='active')
    is_high_priority = models.BooleanField(
        default=False, 
        help_text="High priority geofences get rider assignment preference"
    )
    
    # Performance Tracking
    total_distance_covered = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_verifications = models.PositiveIntegerField(default=0)
    successful_verifications = models.PositiveIntegerField(default=0)
    total_hours_active = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    
    # Metadata
    area_type = models.CharField(
        max_length=50, 
        blank=True,
        help_text="Type of area (commercial, residential, industrial, etc.)"
    )
    target_demographics = models.JSONField(default=dict, blank=True)
    special_instructions = models.TextField(blank=True)
    
    class Meta:
        ordering = ['priority', 'name']
        indexes = [
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['priority', 'is_high_priority']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(max_riders__gte=models.F('min_riders')),
                name='max_riders_gte_min_riders'
            ),
            models.CheckConstraint(
                check=models.Q(current_riders__lte=models.F('max_riders')),
                name='current_riders_lte_max_riders'
            ),
            models.CheckConstraint(
                check=models.Q(budget__gt=0),
                name='budget_positive'
            ),
        ]
    
    def __str__(self):
        return f"{self.campaign.name} - {self.name}"
    
    @property
    def is_active(self):
        from django.utils import timezone
        now = timezone.now()
        return (
            self.status == 'active' and
            self.start_date <= now <= self.end_date and
            self.campaign.is_active
        )
    
    @property
    def available_slots(self):
        return max(0, self.max_riders - self.current_riders)
    
    @property
    def is_full(self):
        return self.current_riders >= self.max_riders
    
    @property
    def fill_percentage(self):
        if self.max_riders == 0:
            return 0
        return (self.current_riders / self.max_riders) * 100
    
    @property
    def budget_utilization(self):
        if self.budget == 0:
            return 0
        return (self.spent / self.budget) * 100
    
    @property
    def remaining_budget(self):
        return max(0, self.budget - self.spent)
    
    @property
    def verification_success_rate(self):
        if self.total_verifications == 0:
            return 0
        return (self.successful_verifications / self.total_verifications) * 100
    
    @property
    def average_hourly_rate(self):
        """Calculate effective hourly rate based on rate type"""
        if self.rate_type == 'per_hour':
            return self.rate_per_hour
        elif self.rate_type == 'fixed_daily':
            target_hours = self.target_coverage_hours or 8
            return self.fixed_daily_rate / target_hours
        elif self.rate_type == 'per_km':
            # Estimate based on average speed (assume 15 km/h for tricycles)
            return self.rate_per_km * 15
        elif self.rate_type == 'hybrid':
            # Return the hour component only for hybrid
            return self.rate_per_hour
        return 0
    
    def can_assign_rider(self):
        """Check if more riders can be assigned to this geofence"""
        return (
            self.is_active and
            not self.is_full and
            self.remaining_budget > 0
        )
    
    def get_rider_earnings_for_distance(self, distance_km, hours_active=0):
        """Calculate rider earnings based on geofence rate type"""
        if self.rate_type == 'per_km':
            return float(self.rate_per_km) * distance_km
        elif self.rate_type == 'per_hour':
            return float(self.rate_per_hour) * hours_active
        elif self.rate_type == 'fixed_daily':
            return float(self.fixed_daily_rate)
        elif self.rate_type == 'hybrid':
            return float(self.rate_per_km) * distance_km + float(self.rate_per_hour) * hours_active
        return 0


class CampaignGeofenceAssignment(BaseModel):
    """
    Track which riders are assigned to which specific geofences
    """
    
    ASSIGNMENT_STATUS = [
        ('assigned', 'Assigned'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Relationships
    campaign_geofence = models.ForeignKey(
        CampaignGeofence,
        on_delete=models.CASCADE,
        related_name='rider_assignments'
    )
    rider = models.ForeignKey(
        'riders.Rider',
        on_delete=models.CASCADE,
        related_name='geofence_assignments'
    )
    campaign_rider_assignment = models.ForeignKey(
        CampaignRiderAssignment,
        on_delete=models.CASCADE,
        related_name='geofence_assignments'
    )
    
    # Assignment Details
    status = models.CharField(max_length=20, choices=ASSIGNMENT_STATUS, default='assigned')
    assigned_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    # Performance in this specific geofence
    distance_covered = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    hours_active = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    verifications_completed = models.PositiveIntegerField(default=0)
    earnings_from_geofence = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Compliance tracking
    compliance_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    last_activity = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        unique_together = ['campaign_geofence', 'rider']
        indexes = [
            models.Index(fields=['campaign_geofence', 'status']),
            models.Index(fields=['rider', 'status']),
            models.Index(fields=['last_activity']),
        ]
    
    def __str__(self):
        return f"{self.rider} in {self.campaign_geofence.name}"
    
    @property
    def is_active(self):
        return self.status == 'active' and self.campaign_geofence.is_active


class PickupLocation(BaseModel):
    """
    Sticker pickup location for each geofence
    One-to-many relationship with CampaignGeofence (multiple pickup locations per geofence)
    """
    
    # Many-to-one relationship with geofence
    geofence = models.ForeignKey(
        CampaignGeofence,
        on_delete=models.CASCADE,
        related_name='pickup_locations'
    )
    
    # Contact Information
    contact_name = models.CharField(
        max_length=100,
        help_text="Contact person at pickup location"
    )
    contact_phone = models.CharField(
        max_length=20,
        help_text="Phone number for pickup coordination"
    )
    
    # Location Details
    address = models.TextField(
        help_text="Full address of pickup location"
    )
    landmark = models.CharField(
        max_length=255,
        blank=True,
        help_text="Nearby landmark for easier location"
    )
    
    # Instructions
    pickup_instructions = models.TextField(
        blank=True,
        help_text="Special instructions for sticker collection"
    )
    
    # Operating Schedule
    operating_hours = models.JSONField(
        default=dict,
        help_text="Operating hours for pickup (e.g., {'monday': '09:00-17:00', 'tuesday': '09:00-17:00'})"
    )
    
    # Availability
    is_active = models.BooleanField(
        default=True,
        help_text="Whether pickup location is currently available"
    )
    
    # Additional Notes
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about the pickup location"
    )
    
    class Meta:
        ordering = ['geofence__priority']
        indexes = [
            models.Index(fields=['geofence']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"Pickup: {self.geofence.name} - {self.contact_name}"
    
    @property
    def full_location_info(self):
        """Get formatted location information for display"""
        info = f"{self.address}"
        if self.landmark:
            info += f" (Near {self.landmark})"
        return info
    
    def get_today_hours(self):
        """Get operating hours for today"""
        from django.utils import timezone
        today = timezone.now().strftime('%A').lower()
        
        # Handle both string and dict formats for operating_hours
        if isinstance(self.operating_hours, dict):
            return self.operating_hours.get(today, 'Closed')
        elif isinstance(self.operating_hours, str):
            # For string format, return the string as-is
            return self.operating_hours
        else:
            return 'Closed'