from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta

from .models import VerificationRequest
from apps.campaigns.models import Campaign, CampaignGeofence


class CreateRandomVerificationSerializer(serializers.Serializer):
    """
    Serializer for creating random verification requests from mobile app
    """
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7)
    accuracy = serializers.DecimalField(max_digits=8, decimal_places=2)
    campaign_id = serializers.UUIDField(required=False, allow_null=True)
    
    def validate(self, attrs):
        """Validate the request data"""
        # Basic location validation
        latitude = float(attrs['latitude'])
        longitude = float(attrs['longitude'])
        accuracy = float(attrs['accuracy'])
        
        if not (-90 <= latitude <= 90):
            raise serializers.ValidationError("Invalid latitude")
        
        if not (-180 <= longitude <= 180):
            raise serializers.ValidationError("Invalid longitude")
        
        if accuracy < 0:
            raise serializers.ValidationError("Accuracy must be positive")
        
        # If campaign_id provided, validate it exists
        if attrs.get('campaign_id'):
            try:
                campaign = Campaign.objects.get(id=attrs['campaign_id'])
                attrs['campaign'] = campaign
            except Campaign.DoesNotExist:
                raise serializers.ValidationError("Campaign not found")
        
        return attrs


class SubmitVerificationSerializer(serializers.Serializer):
    """
    Serializer for submitting verification responses (image + location)
    Enhanced version of existing serializer to handle both random and geofence_join types
    """
    verification_id = serializers.UUIDField()
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7)
    accuracy = serializers.DecimalField(max_digits=8, decimal_places=2)
    timestamp = serializers.DateTimeField()
    image = serializers.ImageField()
    
    def validate_image(self, value):
        """Validate image file - using our fixed validation"""
        if value.size > 5 * 1024 * 1024:  # 5MB limit
            raise serializers.ValidationError("Image file too large (max 5MB)")
        
        # Format validation using file extension since content_type is not available on ImageFieldFile
        if hasattr(value, 'name') and value.name:
            file_extension = value.name.lower().split('.')[-1]
            valid_extensions = ['jpg', 'jpeg', 'png', 'webp']
            if file_extension not in valid_extensions:
                raise serializers.ValidationError(f"Invalid image format. Allowed: {', '.join(valid_extensions)}")
        
        return value
    
    def validate(self, attrs):
        """Validate submission data"""
        # Basic location validation
        latitude = float(attrs['latitude'])
        longitude = float(attrs['longitude'])
        accuracy = float(attrs['accuracy'])
        
        if not (-90 <= latitude <= 90):
            raise serializers.ValidationError("Invalid latitude")
        
        if not (-180 <= longitude <= 180):
            raise serializers.ValidationError("Invalid longitude")
        
        if accuracy < 0:
            raise serializers.ValidationError("Accuracy must be positive")
        
        # Timestamp validation
        timestamp = attrs['timestamp']
        now = timezone.now()
        
        # Allow some time drift (up to 5 minutes in the future or past)
        if timestamp > now + timedelta(minutes=5):
            raise serializers.ValidationError("Timestamp is too far in the future")
        
        if timestamp < now - timedelta(hours=1):
            raise serializers.ValidationError("Timestamp is too old")
        
        return attrs


class VerificationRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for verification request responses
    """
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    geofence_name = serializers.CharField(source='geofence.name', read_only=True, allow_null=True)
    time_remaining_seconds = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = VerificationRequest
        fields = [
            'id', 'verification_type', 'status', 'confidence_score',
            'campaign_name', 'geofence_name', 'created_at', 'attempted_at',
            'can_retry_after', 'retry_count', 'time_remaining_seconds', 
            'is_expired', 'ai_analysis'
        ]
        read_only_fields = ['id', 'created_at', 'attempted_at']
    
    def get_time_remaining_seconds(self, obj):
        """Calculate time remaining for response"""
        if obj.can_retry_after:
            remaining = (obj.can_retry_after - timezone.now()).total_seconds()
            return max(0, int(remaining))
        return 0
    
    def get_is_expired(self, obj):
        """Check if verification has expired"""
        if obj.can_retry_after:
            return timezone.now() > obj.can_retry_after
        # Default 10 minute window
        deadline = obj.created_at + timedelta(minutes=10)
        return timezone.now() > deadline


class PendingVerificationSerializer(serializers.ModelSerializer):
    """
    Simplified serializer for pending verification responses to mobile app
    """
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    geofence_name = serializers.CharField(source='geofence.name', read_only=True, allow_null=True)
    time_remaining_seconds = serializers.SerializerMethodField()
    deadline = serializers.SerializerMethodField()
    
    class Meta:
        model = VerificationRequest
        fields = [
            'id', 'campaign_id', 'campaign_name', 'geofence_name',
            'verification_type', 'status', 'created_at', 
            'time_remaining_seconds', 'deadline'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_time_remaining_seconds(self, obj):
        """Calculate time remaining for response (10 minute window)"""
        deadline = obj.created_at + timedelta(minutes=10)
        remaining = (deadline - timezone.now()).total_seconds()
        return max(0, int(remaining))
    
    def get_deadline(self, obj):
        """Get response deadline"""
        deadline = obj.created_at + timedelta(minutes=10)
        return deadline.isoformat()


class VerificationStatsSerializer(serializers.Serializer):
    """
    Serializer for verification statistics
    """
    total_verifications = serializers.IntegerField()
    passed_verifications = serializers.IntegerField()
    failed_verifications = serializers.IntegerField()
    success_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    average_response_time = serializers.DecimalField(max_digits=8, decimal_places=2)
    last_verification = serializers.DateTimeField(allow_null=True)
    verifications_today = serializers.IntegerField()
    verifications_this_week = serializers.IntegerField()
    current_streak = serializers.IntegerField()


class MobileVerificationRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for verification requests that matches mobile app expectations
    Uses camelCase field names to match mobile app model
    """
    riderId = serializers.CharField(source='rider.id', read_only=True)
    campaignId = serializers.CharField(source='campaign.id', read_only=True)
    campaignName = serializers.CharField(source='campaign.name', read_only=True)
    geofenceId = serializers.CharField(source='geofence.id', read_only=True, allow_null=True)
    geofenceName = serializers.CharField(source='geofence.name', read_only=True, allow_null=True)
    
    # Location fields from the verification request
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    
    # Convert timestamps to ISO format
    timestamp = serializers.DateTimeField()
    deadline = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source='created_at')
    processedAt = serializers.DateTimeField(source='attempted_at', allow_null=True)
    
    # Map verification status to mobile enum values
    status = serializers.SerializerMethodField()
    
    # Additional mobile-specific fields
    isSynced = serializers.SerializerMethodField()
    retryCount = serializers.IntegerField(source='retry_count')
    confidenceScore = serializers.DecimalField(source='confidence_score', max_digits=5, decimal_places=2, allow_null=True)
    aiAnalysis = serializers.JSONField(source='ai_analysis', allow_null=True)
    failureReason = serializers.SerializerMethodField()
    isManualReview = serializers.SerializerMethodField()
    
    class Meta:
        model = VerificationRequest
        fields = [
            'id', 'riderId', 'campaignId', 'campaignName', 'geofenceId', 'geofenceName',
            'latitude', 'longitude', 'accuracy', 'timestamp', 'deadline', 'createdAt', 
            'processedAt', 'status', 'confidenceScore', 'aiAnalysis', 'failureReason',
            'isManualReview', 'isSynced', 'retryCount'
        ]
    
    def get_latitude(self, obj):
        """Extract latitude from PostGIS Point field"""
        if obj.location:
            return obj.location.y  # PostGIS Point.y is latitude
        return 0.0
    
    def get_longitude(self, obj):
        """Extract longitude from PostGIS Point field"""
        if obj.location:
            return obj.location.x  # PostGIS Point.x is longitude
        return 0.0
    
    def get_deadline(self, obj):
        """Calculate deadline (10 minutes from created_at for pending verifications)"""
        if obj.status == 'pending':
            deadline = obj.created_at + timedelta(minutes=10)
        else:
            # For completed verifications, use attempted_at or created_at + 10 min
            deadline = obj.attempted_at or (obj.created_at + timedelta(minutes=10))
        return deadline
    
    def get_status(self, obj):
        """Map Django status to mobile app enum values"""
        status_mapping = {
            'pending': 'pending',
            'processing': 'processing', 
            'passed': 'passed',
            'failed': 'failed',
            'manual_review': 'manualReview'
        }
        return status_mapping.get(obj.status, 'pending')
    
    def get_failureReason(self, obj):
        """Extract failure reason from ai_analysis"""
        if obj.status == 'failed' and obj.ai_analysis:
            return obj.ai_analysis.get('failure_reason')
        return None
    
    def get_isManualReview(self, obj):
        """Check if verification is in manual review"""
        return obj.status == 'manual_review'
    
    def get_isSynced(self, obj):
        """All database records are considered synced"""
        return True