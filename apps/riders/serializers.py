from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Rider, RiderLocation, RiderPerformance, RiderDevice, RiderPayment

User = get_user_model()


class RiderActivationSerializer(serializers.Serializer):
    """Serializer for rider activation with plate number"""
    plate_number = serializers.CharField(
        max_length=8,
        required=True,
        help_text="Tricycle plate number in format ABC123DD"
    )
    device_info = serializers.JSONField(required=False)

    def validate_plate_number(self, value):
        """Validate plate number format and uniqueness"""
        is_valid, message = Rider.validate_plate_number(value)
        if not is_valid:
            raise serializers.ValidationError(message)
        return value.upper().strip()

    def activate_rider(self, rider_instance):
        """Activate the rider with validated plate number"""
        plate_number = self.validated_data['plate_number']
        success, message = rider_instance.activate_with_plate(plate_number)
        
        if not success:
            raise serializers.ValidationError(message)
        
        return rider_instance


class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer for rider profile"""
    full_name = serializers.ReadOnlyField()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name', 
            'full_name', 'phone_number', 'user_type', 'is_verified'
        ]
        read_only_fields = ['id', 'email', 'user_type', 'is_verified']


class RiderSerializer(serializers.ModelSerializer):
    """
    Main rider serializer with all relevant fields
    """
    user = UserSerializer(read_only=True)
    can_activate = serializers.ReadOnlyField()
    can_accept_campaign = serializers.ReadOnlyField()
    active_campaigns_count = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    verification_status_display = serializers.CharField(source='get_verification_status_display', read_only=True)

    class Meta:
        model = Rider
        fields = [
            # Basic Info
            'id', 'user', 'rider_id', 'date_of_birth', 'gender',
            
            # Contact
            'phone_number', 'emergency_contact_name', 'emergency_contact_phone',
            'address', 'city', 'state',
            
            # Tricycle Info
            'tricycle_registration', 'plate_number', 'tricycle_model', 
            'tricycle_year', 'tricycle_color',
            
            # Fleet
            'fleet_owner',
            
            # Status
            'status', 'status_display', 'verification_status', 'verification_status_display',
            'verified_at', 'activated_at', 'activation_attempts',
            
            # Performance
            'rating', 'compliance_score', 'total_campaigns', 'total_earnings', 
            'pending_earnings',
            
            # Proprietary Scores
            'reliability_score', 'route_efficiency_score', 'verification_compliance_score',
            
            # Availability
            'is_available', 'max_concurrent_campaigns',
            
            # Banking
            'bank_name', 'account_number', 'account_name',
            
            # Computed Fields
            'can_activate', 'can_accept_campaign', 'active_campaigns_count',
            
            # Timestamps
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'rider_id', 'activated_at', 'activation_attempts', 
            'total_campaigns', 'total_earnings', 'rating', 'compliance_score',
            'reliability_score', 'route_efficiency_score', 'verification_compliance_score',
            'verified_at', 'created_at', 'updated_at'
        ]

    def get_active_campaigns_count(self, obj):
        return obj.current_campaign_count


class RiderSummarySerializer(serializers.ModelSerializer):
    """
    Lightweight rider serializer for lists and summaries
    """
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    verification_status_display = serializers.CharField(source='get_verification_status_display', read_only=True)

    class Meta:
        model = Rider
        fields = [
            'id', 'rider_id', 'user_name', 'phone_number',
            'status', 'status_display', 'verification_status', 'verification_status_display',
            'plate_number', 'rating', 'total_campaigns', 'total_earnings',
            'is_available', 'created_at'
        ]


class RiderLocationSerializer(serializers.ModelSerializer):
    """Serializer for rider location tracking"""
    
    class Meta:
        model = RiderLocation
        fields = [
            'id', 'rider', 'location', 'accuracy', 'speed', 'heading', 
            'altitude', 'timestamp', 'is_working', 'current_campaign',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class RiderPerformanceSerializer(serializers.ModelSerializer):
    """Serializer for rider performance metrics"""
    rider_name = serializers.CharField(source='rider.user.get_full_name', read_only=True)
    
    class Meta:
        model = RiderPerformance
        fields = [
            'id', 'rider', 'rider_name', 'period_start', 'period_end', 'period_type',
            'campaigns_completed', 'total_verifications', 'successful_verifications',
            'verification_success_rate', 'total_distance', 'unique_areas_visited',
            'average_daily_distance', 'total_earnings', 'bonus_earnings',
            'compliance_score', 'violations', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class RiderDeviceSerializer(serializers.ModelSerializer):
    """Serializer for rider mobile devices"""
    
    class Meta:
        model = RiderDevice
        fields = [
            'id', 'rider', 'device_id', 'device_name', 'platform', 
            'os_version', 'app_version', 'is_active', 'last_login',
            'fcm_token', 'notifications_enabled', 'location_sharing_enabled',
            'preferred_language', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class RiderPaymentSerializer(serializers.ModelSerializer):
    """Serializer for rider payments"""
    rider_name = serializers.CharField(source='rider.user.get_full_name', read_only=True)
    payment_type_display = serializers.CharField(source='get_payment_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = RiderPayment
        fields = [
            'id', 'rider', 'rider_name', 'payment_type', 'payment_type_display',
            'amount', 'currency', 'reference', 'status', 'status_display',
            'payment_method', 'external_reference', 'campaign', 'processed_at',
            'failure_reason', 'retry_count', 'created_at'
        ]
        read_only_fields = [
            'id', 'reference', 'processed_at', 'failure_reason', 
            'retry_count', 'created_at'
        ]


class PlateNumberValidationSerializer(serializers.Serializer):
    """Serializer for validating plate numbers without activation"""
    plate_number = serializers.CharField(
        max_length=8,
        required=True,
        help_text="Tricycle plate number in format ABC123DD"
    )

    def validate_plate_number(self, value):
        """Validate plate number format and uniqueness"""
        is_valid, message = Rider.validate_plate_number(value)
        if not is_valid:
            raise serializers.ValidationError(message)
        return value.upper().strip()