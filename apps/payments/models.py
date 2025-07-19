from django.db import models
from apps.core.models import BaseModel

class Payment(BaseModel):
    """Payment transactions in the platform"""
    
    PAYMENT_TYPES = [
        ('campaign_payment', 'Campaign Payment'),
        ('agency_deposit', 'Agency Deposit'),
        ('platform_fee', 'Platform Fee'),
        ('refund', 'Refund'),
    ]
    
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    reference = models.CharField(max_length=100, unique=True)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    
    # Relationships
    payer = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='payments_made')
    recipient = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='payments_received', null=True, blank=True)
    campaign = models.ForeignKey('campaigns.Campaign', on_delete=models.CASCADE, null=True, blank=True)
    
    # Payment Gateway Data
    external_reference = models.CharField(max_length=100, blank=True)
    gateway_response = models.JSONField(default=dict)
    
    def __str__(self):
        return f"Payment {self.reference} - {self.amount}"