from rest_framework import serializers
from django.contrib.gis.geos import Point
from .models import (
    LocationRecord, GeofenceEntry, RiderSession, 
    EarningsCalculation, LocationSyncBatch, DailyTrackingSummary
)


class LocationRecordSerializer(serializers.ModelSerializer):
    """
    Serializer for location records from mobile app
    Handles conversion between mobile format and server format
    """
    
    # Mobile app sends lat/lng separately, we convert to Point
    latitude = serializers.FloatField(write_only=True)
    longitude = serializers.FloatField(write_only=True)
    
    class Meta:
        model = LocationRecord
        fields = [
            'id', 'mobile_id', 'latitude', 'longitude', 'accuracy',
            'speed', 'heading', 'altitude', 'recorded_at', 'is_working',
            'metadata', 'sync_status', 'synced_at'
        ]
        read_only_fields = ['id', 'synced_at', 'sync_status']
    
    def create(self, validated_data):
        """Create location record with Point geometry"""
        latitude = validated_data.pop('latitude')
        longitude = validated_data.pop('longitude')
        
        # Create Point geometry
        validated_data['location'] = Point(longitude, latitude)
        
        return super().create(validated_data)
    
    def to_representation(self, instance):
        """Convert Point back to lat/lng for API responses"""
        data = super().to_representation(instance)
        if instance.location:
            data['latitude'] = instance.location.y
            data['longitude'] = instance.location.x
        return data


class LocationSyncRequestSerializer(serializers.Serializer):
    """
    Serializer for batch location sync requests from mobile app
    """
    
    batch_id = serializers.CharField(max_length=36)
    batch_created_at = serializers.DateTimeField()
    locations = LocationRecordSerializer(many=True)
    
    def validate_locations(self, locations):
        """Validate location data"""
        if not locations:
            raise serializers.ValidationError("At least one location is required")
        
        if len(locations) > 100:
            raise serializers.ValidationError("Maximum 100 locations per batch")
        
        # Check for duplicate mobile_ids within batch
        mobile_ids = [loc['mobile_id'] for loc in locations]
        if len(mobile_ids) != len(set(mobile_ids)):
            raise serializers.ValidationError("Duplicate mobile_ids in batch")
        
        return locations


class LocationSyncResponseSerializer(serializers.Serializer):
    """
    Response serializer for location sync
    """
    
    batch_id = serializers.CharField()
    status = serializers.CharField()
    processed_count = serializers.IntegerField()
    failed_count = serializers.IntegerField()
    errors = serializers.ListField(child=serializers.DictField(), required=False)


class GeofenceEntrySerializer(serializers.ModelSerializer):
    """
    Serializer for geofence entry/exit events
    """
    
    rider_id = serializers.CharField(source='rider.rider_id', read_only=True)
    geofence_name = serializers.CharField(source='geofence.name', read_only=True)
    
    class Meta:
        model = GeofenceEntry
        fields = [
            'id', 'rider_id', 'geofence_name', 'entry_type',
            'location', 'recorded_at'
        ]


class RiderSessionSerializer(serializers.ModelSerializer):
    """
    Serializer for rider work sessions
    """
    
    rider_id = serializers.CharField(source='rider.rider_id', read_only=True)
    geofence_name = serializers.CharField(source='geofence.name', read_only=True)
    
    class Meta:
        model = RiderSession
        fields = [
            'id', 'rider_id', 'geofence_name', 'started_at', 'ended_at',
            'duration_minutes', 'distance_covered', 'verification_count',
            'earnings_calculated', 'status'
        ]


class EarningsCalculationSerializer(serializers.ModelSerializer):
    """
    Serializer for earnings calculations
    """
    
    rider_id = serializers.CharField(source='rider.rider_id', read_only=True)
    geofence_name = serializers.CharField(source='geofence.name', read_only=True)
    campaign_name = serializers.CharField(source='geofence.campaign.name', read_only=True)
    
    class Meta:
        model = EarningsCalculation
        fields = [
            'id', 'mobile_id', 'rider_id', 'geofence_name', 'campaign_name',
            'earnings_type', 'amount', 'currency', 'distance_km', 'duration_hours',
            'rate_applied', 'earned_at', 'status', 'verifications_completed'
        ]


class DailyTrackingSummarySerializer(serializers.ModelSerializer):
    """
    Serializer for daily tracking summaries
    """
    
    rider_id = serializers.CharField(source='rider.rider_id', read_only=True)
    
    class Meta:
        model = DailyTrackingSummary
        fields = [
            'id', 'rider_id', 'date', 'total_locations_recorded',
            'total_distance_km', 'working_hours', 'geofences_visited',
            'geofence_entries', 'geofence_exits', 'total_sessions',
            'completed_sessions', 'abandoned_sessions', 'total_earnings',
            'distance_earnings', 'time_earnings', 'bonus_earnings',
            'verifications_completed', 'sync_batches_count', 'sync_success_rate'
        ]


class LocationSyncBatchSerializer(serializers.ModelSerializer):
    """
    Serializer for sync batch information
    """
    
    rider_id = serializers.CharField(source='rider.rider_id', read_only=True)
    
    class Meta:
        model = LocationSyncBatch
        fields = [
            'id', 'batch_id', 'rider_id', 'total_records', 'processed_records',
            'failed_records', 'batch_created_at', 'received_at', 'status',
            'success_rate'
        ]


class EarningsRequestSerializer(serializers.Serializer):
    """
    Serializer for earnings calculation requests from mobile
    """
    
    mobile_id = serializers.CharField(max_length=36)
    geofence_id = serializers.IntegerField()
    earnings_type = serializers.ChoiceField(choices=EarningsCalculation.EARNINGS_TYPE_CHOICES)
    distance_km = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    duration_hours = serializers.DecimalField(max_digits=8, decimal_places=2, default=0)
    verifications_completed = serializers.IntegerField(default=0)
    earned_at = serializers.DateTimeField()
    metadata = serializers.JSONField(default=dict)


class TrackingStatsSerializer(serializers.Serializer):
    """
    Serializer for rider tracking statistics
    """
    
    today_distance = serializers.DecimalField(max_digits=10, decimal_places=2)
    today_earnings = serializers.DecimalField(max_digits=10, decimal_places=2)
    today_sessions = serializers.IntegerField()
    week_distance = serializers.DecimalField(max_digits=10, decimal_places=2)
    week_earnings = serializers.DecimalField(max_digits=10, decimal_places=2)
    month_distance = serializers.DecimalField(max_digits=10, decimal_places=2)
    month_earnings = serializers.DecimalField(max_digits=10, decimal_places=2)
    active_geofences = serializers.ListField(child=serializers.CharField())
    pending_sync_count = serializers.IntegerField()
    last_sync = serializers.DateTimeField(allow_null=True)