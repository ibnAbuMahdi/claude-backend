from django.db import models
from django.core.validators import RegexValidator
from django.contrib.gis.db import models as gis_models
from apps.core.models import BaseModel
import secrets
import string

class Agency(BaseModel):
    """
    Advertising Agency model - Primary customer in B2B2B model
    Each agency gets white-label access and multi-client management
    """
    
    AGENCY_TYPES = [
        ('digital', 'Digital Agency'),
        ('traditional', 'Traditional Agency'),
        ('full_service', 'Full Service Agency'),
        ('boutique', 'Boutique Agency'),
        ('in_house', 'In-House Team'),
    ]
    
    SUBSCRIPTION_TIERS = [
        ('starter', 'Starter'),
        ('professional', 'Professional'),
        ('enterprise', 'Enterprise'),
        ('custom', 'Custom'),
    ]
    
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    subdomain = models.CharField(
        max_length=63,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$',
                message='Subdomain must be lowercase alphanumeric with optional hyphens'
            )
        ]
    )
    
    # Business Information
    agency_type = models.CharField(max_length=20, choices=AGENCY_TYPES)
    registration_number = models.CharField(max_length=50, blank=True)
    tax_id = models.CharField(max_length=50, blank=True)
    website = models.URLField(blank=True)
    description = models.TextField(blank=True)
    
    # Contact Information
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='Nigeria')
    
    # Platform Configuration
    subscription_tier = models.CharField(max_length=20, choices=SUBSCRIPTION_TIERS, default='starter')
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    api_rate_limit = models.IntegerField(default=1000)
    max_campaigns = models.IntegerField(default=50)
    monthly_spend_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # White-label Settings
    logo = models.ImageField(upload_to='agency_logos/', blank=True, null=True)
    primary_color = models.CharField(max_length=7, default='#1976d2')  # Hex color
    secondary_color = models.CharField(max_length=7, default='#dc004e')
    custom_domain = models.CharField(max_length=255, blank=True)
    
    # API Access
    api_enabled = models.BooleanField(default=False)
    webhook_url = models.URLField(blank=True)
    
    # Financial
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=7.50)  # Platform take rate
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_spend = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_campaigns = models.IntegerField(default=0)
    
    # Defensive Features (as per plan)
    exclusive_zones = gis_models.MultiPolygonField(blank=True, null=True)
    locked_in_until = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['subdomain']),
            models.Index(fields=['subscription_tier', 'created_at']),
        ]
    
    def __str__(self):
        return self.name
    
    def generate_api_key(self):
        """Generate a new API key for this agency"""
        return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(40))
    
    @property
    def active_campaigns(self):
        return self.campaigns.filter(status='active').count()

class AgencyAPIKey(BaseModel):
    """API keys for agency integrations"""
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name='api_keys')
    name = models.CharField(max_length=100)
    key = models.CharField(max_length=40, unique=True)
    is_active = models.BooleanField(default=True)
    last_used = models.DateTimeField(null=True, blank=True)
    permissions = models.JSONField(default=dict)  # Store specific permissions
    
    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.agency.generate_api_key()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.agency.name} - {self.name}"

class AgencyClient(BaseModel):
    """
    Clients that agencies manage campaigns for
    This represents the actual advertisers (end customers)
    """
    
    CLIENT_TYPES = [
        ('sme', 'Small/Medium Enterprise'),
        ('corporate', 'Corporate'),
        ('nonprofit', 'Non-Profit'),
        ('government', 'Government'),
        ('startup', 'Startup'),
    ]
    
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name='clients')
    name = models.CharField(max_length=255)
    slug = models.SlugField()
    client_type = models.CharField(max_length=20, choices=CLIENT_TYPES)
    
    # Contact Information
    contact_person = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    
    # Business Information
    industry = models.CharField(max_length=100)
    website = models.URLField(blank=True)
    description = models.TextField(blank=True)
    average_campaign_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Optional platform access (as per plan)
    has_platform_access = models.BooleanField(default=False)
    view_only_user = models.OneToOneField(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='client_profile'
    )
    
    # Campaign Settings
    monthly_budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    preferred_locations = models.JSONField(default=list)  # List of preferred areas
    brand_guidelines = models.TextField(blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['agency', 'slug']
    
    def __str__(self):
        return f"{self.name} ({self.agency.name})"
    
    @property
    def total_campaigns(self):
        return self.campaigns.count()
    
    @property
    def total_spend(self):
        from django.db.models import Sum
        return self.campaigns.aggregate(
            total=Sum('total_budget')
        )['total'] or 0

class AgencySettings(BaseModel):
    """Agency-specific platform settings and preferences"""
    agency = models.OneToOneField(Agency, on_delete=models.CASCADE, related_name='settings')
    
    # Notification Settings
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    webhook_notifications = models.BooleanField(default=False)
    
    # Campaign Defaults
    default_campaign_duration = models.PositiveIntegerField(default=30)  # days
    auto_approve_campaigns = models.BooleanField(default=False)
    require_client_approval = models.BooleanField(default=True)
    
    # Reporting Settings
    report_frequency = models.CharField(
        max_length=20,
        choices=[
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
        ],
        default='weekly'
    )
    include_rider_details = models.BooleanField(default=False)
    white_label_reports = models.BooleanField(default=True)
    
    # Financial Settings
    auto_payment_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=1000)
    payment_terms = models.PositiveIntegerField(default=7)  # days
    
    def __str__(self):
        return f"Settings for {self.agency.name}"

# Defensive Architecture Models (from plan)
class ExclusiveContract(BaseModel):
    """Lock in key partners"""
    
    PARTNER_TYPES = [
        ('fleet', 'Fleet Owner'),
        ('agency', 'Agency'),
        ('advertiser', 'Advertiser'),
    ]
    
    partner_type = models.CharField(max_length=20, choices=PARTNER_TYPES)
    partner_id = models.UUIDField()
    
    # Contract terms
    start_date = models.DateField()
    end_date = models.DateField()
    exclusivity_radius = models.IntegerField(help_text="Kilometers")
    auto_renew = models.BooleanField(default=False)
    
    # Penalties
    early_termination_penalty = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Benefits
    guaranteed_minimum_revenue = models.DecimalField(max_digits=10, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    
    # Performance bonuses
    volume_bonuses = models.JSONField(default=dict)
    
    def __str__(self):
        return f"Exclusive {self.partner_type} contract - {self.partner_id}"

class CompetitiveIntelligence(BaseModel):
    """Collect data that competitors can't replicate"""
    
    # Route effectiveness by time and day
    route_patterns = models.JSONField(default=dict)
    
    # Advertiser behavior patterns
    campaign_patterns = models.JSONField(default=dict)
    
    # Rider reliability patterns
    rider_patterns = models.JSONField(default=dict)
    
    # Market pricing intelligence
    pricing_patterns = models.JSONField(default=dict)
    
    # Market analysis date
    analysis_date = models.DateField(auto_now_add=True)
    
    class Meta:
        ordering = ['-analysis_date']
    
    def __str__(self):
        return f"Market Intelligence - {self.analysis_date}"

class AuditLog(BaseModel):
    """Comprehensive audit logging"""
    user = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50)
    model = models.CharField(max_length=50)
    object_id = models.CharField(max_length=50)
    changes = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['model', 'object_id']),
        ]
    
    def __str__(self):
        return f"{self.action} on {self.model} by {self.user}"