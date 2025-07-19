from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid

class TimeStampedModel(models.Model):
    """Abstract base model with created_at and updated_at fields"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True

class UUIDModel(models.Model):
    """Abstract base model with UUID primary key"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    class Meta:
        abstract = True

class BaseModel(UUIDModel, TimeStampedModel):
    """Base model combining UUID and timestamp functionality"""
    
    class Meta:
        abstract = True