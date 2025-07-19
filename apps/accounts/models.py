import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
from apps.core.models import BaseModel

class User(AbstractUser):
    """
    Custom user model for Stika platform
    Supports different user types: Agency Admin, Fleet Owner, Rider, Admin
    """
    
    USER_TYPES = [
        ('agency_admin', 'Agency Admin'),
        ('agency_staff', 'Agency Staff'),
        ('fleet_owner', 'Fleet Owner'),
        ('rider', 'Rider'),
        ('admin', 'Platform Admin'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone_number = PhoneNumberField(blank=True, null=True)
    user_type = models.CharField(max_length=20, choices=USER_TYPES)
    is_verified = models.BooleanField(default=False)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    address = models.TextField(blank=True)
    
    # Agency relationship (for agency users)
    agency = models.ForeignKey(
        'agencies.Agency',
        on_delete=models.CASCADE,
        related_name='users',
        blank=True,
        null=True
    )
    
    # Fleet relationship (for fleet owners and riders)
    fleet_owner = models.ForeignKey(
        'fleets.FleetOwner',
        on_delete=models.CASCADE,
        related_name='users',
        blank=True,
        null=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'user_type']
    
    def __str__(self):
        return f"{self.email} ({self.get_user_type_display()})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

class UserProfile(BaseModel):
    """Extended profile information for users"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(blank=True, max_length=500)
    nin = models.CharField(max_length=11, blank=True)  # Nigerian National ID
    bvn = models.CharField(max_length=11, blank=True)  # Bank Verification Number
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = PhoneNumberField(blank=True, null=True)
    preferred_language = models.CharField(
        max_length=10,
        choices=[('en', 'English'), ('yo', 'Yoruba'), ('ig', 'Igbo'), ('ha', 'Hausa')],
        default='en'
    )
    
    def __str__(self):
        return f"Profile of {self.user.email}"