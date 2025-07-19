from django.db import models
from apps.core.models import BaseModel

class FleetOwner(BaseModel):
    """Fleet partners who control multiple riders (as per plan)"""
    
    FLEET_STATUS = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, unique=True)
    email = models.EmailField()
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    
    # Business details (as per plan)
    company_name = models.CharField(max_length=255, blank=True)
    fleet_size = models.IntegerField(default=0)
    business_type = models.CharField(max_length=100)
    years_in_operation = models.PositiveIntegerField()
    
    # Partnership terms (as per plan)
    is_exclusive = models.BooleanField(default=False)
    exclusive_until = models.DateTimeField(null=True, blank=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=2.5)
    
    # Performance bonus tracking (as per plan)
    total_rider_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    performance_bonus_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Anti-poaching features (as per plan)
    locked_riders = models.BooleanField(default=False)
    penalty_amount = models.DecimalField(max_digits=10, decimal_places=2, default=100000)
    
    # Platform Status
    status = models.CharField(max_length=20, choices=FLEET_STATUS, default='active')
    
    def __str__(self):
        return self.name

# Keep Fleet for backward compatibility
Fleet = FleetOwner