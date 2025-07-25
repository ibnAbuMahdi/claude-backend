from rest_framework import serializers
from .models import Campaign, CampaignRiderAssignment, CampaignGeofence, CampaignGeofenceAssignment
from apps.agencies.models import AgencyClient
from django.utils import timezone


class AgencyClientSerializer(serializers.ModelSerializer):
    """Simple client serializer for campaign responses"""
    
    class Meta:
        model = AgencyClient
        fields = ['id', 'name', 'industry', 'client_type']


class CampaignGeofenceSerializer(serializers.ModelSerializer):
    """Serializer for individual campaign geofences"""
    
    # Mobile app compatibility fields
    centerLatitude = serializers.DecimalField(source='center_latitude', max_digits=10, decimal_places=7)
    centerLongitude = serializers.DecimalField(source='center_longitude', max_digits=10, decimal_places=7)
    radius = serializers.IntegerField(source='radius_meters')
    
    # Additional computed fields
    available_slots = serializers.ReadOnlyField()
    fill_percentage = serializers.ReadOnlyField()
    budget_utilization = serializers.ReadOnlyField()
    remaining_budget = serializers.ReadOnlyField()
    verification_success_rate = serializers.ReadOnlyField()
    average_hourly_rate = serializers.ReadOnlyField()
    
    # Status fields
    is_active = serializers.ReadOnlyField()
    is_full = serializers.ReadOnlyField()
    can_assign_rider = serializers.ReadOnlyField()
    
    class Meta:
        model = CampaignGeofence
        fields = [
            'id', 'name', 'description', 'priority', 'centerLatitude', 'centerLongitude',
            'radius', 'budget', 'spent', 'rate_type', 'rate_per_km', 'rate_per_hour',
            'fixed_daily_rate', 'start_date', 'end_date', 'max_riders', 'current_riders',
            'min_riders', 'target_coverage_hours', 'verification_frequency', 'status',
            'is_high_priority', 'total_distance_covered', 'total_verifications',
            'successful_verifications', 'total_hours_active', 'area_type',
            'target_demographics', 'special_instructions', 'available_slots',
            'fill_percentage', 'budget_utilization', 'remaining_budget',
            'verification_success_rate', 'average_hourly_rate', 'is_active',
            'is_full', 'can_assign_rider', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'current_riders', 'total_distance_covered', 'total_verifications',
            'successful_verifications', 'total_hours_active', 'spent', 'created_at', 'updated_at'
        ]


class CampaignGeofenceAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for geofence-specific rider assignments"""
    
    geofence_name = serializers.CharField(source='campaign_geofence.name', read_only=True)
    rider_name = serializers.CharField(source='rider.user.get_full_name', read_only=True)
    rider_id = serializers.CharField(source='rider.rider_id', read_only=True)
    
    class Meta:
        model = CampaignGeofenceAssignment
        fields = [
            'id', 'geofence_name', 'rider_name', 'rider_id', 'status',
            'assigned_at', 'started_at', 'completed_at', 'distance_covered',
            'hours_active', 'verifications_completed', 'earnings_from_geofence',
            'compliance_score', 'last_activity', 'is_active'
        ]
        read_only_fields = [
            'id', 'assigned_at', 'started_at', 'completed_at', 'last_activity', 'is_active'
        ]


class CampaignSerializer(serializers.ModelSerializer):
    """Serializer for campaign listing and details - aligned with mobile app"""
    
    clientName = serializers.CharField(source='client.name', read_only=True)
    agencyId = serializers.CharField(source='agency.id', read_only=True)
    agencyName = serializers.CharField(source='agency.name', read_only=True)
    stickerImageUrl = serializers.CharField(source='sticker_design', read_only=True)
    
    # Map backend fields to mobile app expectations
    ratePerKm = serializers.SerializerMethodField('get_rate_per_km')
    ratePerHour = serializers.SerializerMethodField('get_rate_per_hour')
    fixedDailyRate = serializers.CharField(source='platform_rate', read_only=True)
    maxRiders = serializers.CharField(source='required_riders', read_only=True)
    currentRiders = serializers.SerializerMethodField('get_current_riders')
    area = serializers.SerializerMethodField('get_area')
    targetAudiences = serializers.SerializerMethodField('get_target_audiences')
    estimatedWeeklyEarnings = serializers.SerializerMethodField('get_estimated_weekly_earnings')
    budget = serializers.CharField(source='total_budget', read_only=True)
    spent = serializers.DecimalField(max_digits=12, decimal_places=2, default=0, read_only=True)
    totalVerifications = serializers.IntegerField(default=0, read_only=True)
    totalDistanceCovered = serializers.FloatField(default=0.0, read_only=True)
    
    # Mobile app expects these fields
    isActive = serializers.SerializerMethodField('get_is_active')
    canJoin = serializers.SerializerMethodField('get_can_join')
    
    # Requirements and geofences (simplified for now)
    requirements = serializers.SerializerMethodField('get_requirements')
    geofences = serializers.SerializerMethodField('get_geofences')
    
    # Override status to map backend values to mobile app expectations
    status = serializers.SerializerMethodField('get_status')
    
    # DateTime fields with camelCase names
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)
    startDate = serializers.DateTimeField(source='start_date', read_only=True)
    endDate = serializers.DateTimeField(source='end_date', read_only=True)
    
    class Meta:
        model = Campaign
        fields = [
            'id', 'name', 'description', 'clientName', 'agencyId', 
            'agencyName', 'stickerImageUrl', 'ratePerKm', 'ratePerHour',
            'fixedDailyRate', 'startDate', 'endDate', 'status',
            'geofences', 'maxRiders', 'currentRiders', 'requirements',
            'estimatedWeeklyEarnings', 'area', 'targetAudiences',
            'createdAt', 'updatedAt', 'isActive', 'totalVerifications',
            'totalDistanceCovered', 'budget', 'spent', 'canJoin',
            'campaign_type'
        ]
        read_only_fields = ['id', 'createdAt', 'updatedAt']
    
    def get_rate_per_km(self, obj):
        """Calculate rate per km based on platform rate - realistic value"""
        # Convert daily rate to per-km rate (assuming average 50km per day)
        daily_rate = float(obj.platform_rate)
        return round(daily_rate / 50.0, 2)  # ₦160-400 per km depending on campaign
    
    def get_rate_per_hour(self, obj):
        """Calculate rate per hour based on platform rate - realistic value"""
        # Convert daily rate to hourly rate (assuming 8 working hours per day)
        daily_rate = float(obj.platform_rate)
        return round(daily_rate / 8.0, 2)  # ₦1000-2500 per hour depending on campaign
    
    def get_current_riders(self, obj):
        """Get number of riders already joined"""
        return obj.assigned_riders.filter(
            campaignriderassignment__status__in=['assigned', 'accepted', 'active']
        ).count()
    
    def get_area(self, obj):
        """Get campaign area from target cities"""
        return ', '.join(obj.target_cities) if obj.target_cities else 'Lagos'
    
    def get_target_audiences(self, obj):
        """Convert target audience to list"""
        if obj.target_audience:
            return [obj.target_audience]
        return []
    
    def get_estimated_weekly_earnings(self, obj):
        """Calculate estimated weekly earnings"""
        return float(obj.platform_rate * 7)  # 7 days worth
    
    def get_is_active(self, obj):
        """Check if campaign is currently active"""
        now = timezone.now()
        return (
            obj.status == 'active' and
            obj.start_date <= now <= obj.end_date
        )
    
    def get_can_join(self, obj):
        """Check if campaign can accept more riders"""
        current_riders = self.get_current_riders(obj)
        return (
            obj.status == 'active' and
            self.get_is_active(obj) and
            current_riders < obj.required_riders
        )
    
    def get_requirements(self, obj):
        """Default campaign requirements"""
        return {
            'min_rating': 0,
            'min_completed_campaigns': 0,
            'requires_verification': True,
            'required_documents': [],
            'min_age': 18,
            'requires_smartphone': True,
            'allowed_vehicle_types': ['tricycle']
        }
    
    def get_geofences(self, obj):
        """Return campaign geofences from new CampaignGeofence model"""
        geofences = []
        
        # Get geofences from the new CampaignGeofence model
        campaign_geofences = obj.geofences.all().order_by('priority', 'name')
        
        for geofence in campaign_geofences:
            # Convert geofence polygon to coordinate list for mobile app
            coordinates = []
            if geofence.geofence_data:
                coords = geofence.geofence_data.coords[0]  # Exterior ring coordinates
                coordinates = [
                    {"lat": lat, "lng": lng} for lng, lat in coords[:-1]  # Exclude last duplicate point
                ]
            
            geofences.append({
                "id": str(geofence.id),
                "name": geofence.name,
                "centerLatitude": float(geofence.center_latitude),
                "centerLongitude": float(geofence.center_longitude),
                "radius": geofence.radius_meters,
                "shape": "circle",  # Default to circle for mobile app compatibility
                "polygonPoints": coordinates if coordinates else None,
                
                # Financial details per geofence
                "budget": float(geofence.budget),
                "spent": float(geofence.spent),
                "remainingBudget": float(geofence.remaining_budget),
                
                # Rate information
                "rateType": geofence.rate_type,
                "ratePerKm": float(geofence.rate_per_km),
                "ratePerHour": float(geofence.rate_per_hour),
                "fixedDailyRate": float(geofence.fixed_daily_rate),
                
                # Duration
                "startDate": geofence.start_date.isoformat(),
                "endDate": geofence.end_date.isoformat(),
                
                # Rider limits
                "maxRiders": geofence.max_riders,
                "currentRiders": geofence.current_riders,
                "availableSlots": geofence.available_slots,
                "minRiders": geofence.min_riders,
                
                # Status
                "status": geofence.status,
                "isActive": geofence.is_active,
                "isHighPriority": geofence.is_high_priority,
                "priority": geofence.priority,
                
                # Performance
                "fillPercentage": geofence.fill_percentage,
                "budgetUtilization": geofence.budget_utilization,
                "verificationSuccessRate": geofence.verification_success_rate,
                "averageHourlyRate": float(geofence.average_hourly_rate),
                
                # Additional info
                "areaType": geofence.area_type,
                "targetCoverageHours": geofence.target_coverage_hours,
                "verificationFrequency": geofence.verification_frequency,
                "specialInstructions": geofence.special_instructions,
            })
        
        # Fallback: if no geofences in new model, create from legacy data or defaults
        if not geofences:
            # Try to get from legacy target_areas field
            if obj.target_areas:
                area_names = {
                    0: {"name": "Victoria Island", "radius": 3000},
                    1: {"name": "Ikeja", "radius": 4000},
                    2: {"name": "Surulere", "radius": 3500},
                    3: {"name": "Lagos Island", "radius": 2000},
                }
                
                for i, polygon in enumerate(obj.target_areas):
                    if i < len(area_names):
                        area_info = area_names[i]
                        centroid = polygon.centroid
                        coords = polygon.coords[0]
                        
                        # Calculate budget per geofence (split evenly)
                        budget_per_geofence = float(obj.total_budget) / len(obj.target_areas)
                        riders_per_geofence = max(1, obj.required_riders // len(obj.target_areas))
                        
                        geofences.append({
                            "id": f"legacy_{i}",
                            "name": area_info["name"],
                            "centerLatitude": centroid.y,
                            "centerLongitude": centroid.x,
                            "radius": area_info["radius"],
                            "shape": "polygon",
                            "polygonPoints": [{"lat": lat, "lng": lng} for lng, lat in coords[:-1]],
                            
                            # Split campaign budget/riders evenly
                            "budget": budget_per_geofence,
                            "spent": 0,
                            "remainingBudget": budget_per_geofence,
                            
                            # Use campaign rates
                            "rateType": "per_km",
                            "ratePerKm": self.get_rate_per_km(obj),
                            "ratePerHour": self.get_rate_per_hour(obj),
                            "fixedDailyRate": float(obj.platform_rate),
                            
                            # Use campaign duration
                            "startDate": obj.start_date.isoformat(),
                            "endDate": obj.end_date.isoformat(),
                            
                            # Split riders
                            "maxRiders": riders_per_geofence,
                            "currentRiders": 0,
                            "availableSlots": riders_per_geofence,
                            "minRiders": 1,
                            
                            # Default status
                            "status": "active",
                            "isActive": obj.is_active,
                            "isHighPriority": i == 0,
                            "priority": i + 1,
                            
                            # Default performance
                            "fillPercentage": 0,
                            "budgetUtilization": 0,
                            "verificationSuccessRate": 100,
                            "averageHourlyRate": self.get_rate_per_hour(obj),
                            
                            "areaType": "mixed",
                            "targetCoverageHours": 8,
                            "verificationFrequency": obj.verification_frequency,
                            "specialInstructions": "",
                        })
            else:
                # Create default geofences based on budget
                budget = float(obj.total_budget)
                default_geofences_data = [
                    {
                        "name": "Victoria Island", 
                        "centerLatitude": 6.4269, "centerLongitude": 3.4105,
                        "radius": 3000, "priority": 1
                    },
                    {
                        "name": "Ikeja",
                        "centerLatitude": 6.6018, "centerLongitude": 3.3515,
                        "radius": 4000, "priority": 2
                    }
                ]
                
                if budget >= 200000:
                    default_geofences_data.extend([
                        {
                            "name": "Surulere",
                            "centerLatitude": 6.4969, "centerLongitude": 3.3603,
                            "radius": 3500, "priority": 3
                        },
                        {
                            "name": "Lagos Island",
                            "centerLatitude": 6.4541, "centerLongitude": 3.3947,
                            "radius": 2000, "priority": 4
                        }
                    ])
                elif budget >= 100000:
                    default_geofences_data.append({
                        "name": "Surulere",
                        "centerLatitude": 6.4969, "centerLongitude": 3.3603,
                        "radius": 3500, "priority": 3
                    })
                
                # Create default geofences
                budget_per_geofence = budget / len(default_geofences_data)
                riders_per_geofence = max(1, obj.required_riders // len(default_geofences_data))
                
                for i, gf_data in enumerate(default_geofences_data):
                    geofences.append({
                        "id": f"default_{i}",
                        "name": gf_data["name"],
                        "centerLatitude": gf_data["centerLatitude"],
                        "centerLongitude": gf_data["centerLongitude"],
                        "radius": gf_data["radius"],
                        "shape": "circle",
                        "polygonPoints": None,
                        
                        "budget": budget_per_geofence,
                        "spent": 0,
                        "remainingBudget": budget_per_geofence,
                        
                        "rateType": "per_km",
                        "ratePerKm": self.get_rate_per_km(obj),
                        "ratePerHour": self.get_rate_per_hour(obj),
                        "fixedDailyRate": float(obj.platform_rate),
                        
                        "startDate": obj.start_date.isoformat(),
                        "endDate": obj.end_date.isoformat(),
                        
                        "maxRiders": riders_per_geofence,
                        "currentRiders": 0,
                        "availableSlots": riders_per_geofence,
                        "minRiders": 1,
                        
                        "status": "active",
                        "isActive": obj.is_active,
                        "isHighPriority": i == 0,
                        "priority": gf_data["priority"],
                        
                        "fillPercentage": 0,
                        "budgetUtilization": 0,
                        "verificationSuccessRate": 100,
                        "averageHourlyRate": self.get_rate_per_hour(obj),
                        
                        "areaType": "mixed",
                        "targetCoverageHours": 8,
                        "verificationFrequency": obj.verification_frequency,
                        "specialInstructions": "",
                    })
            
        return geofences
    
    def get_status(self, obj):
        """Map backend status to mobile app status"""
        status_mapping = {
            'draft': 'draft',
            'pending_approval': 'pending',
            'approved': 'pending', 
            'active': 'running',
            'paused': 'paused',
            'completed': 'completed',
            'cancelled': 'cancelled'
        }
        return status_mapping.get(obj.status, obj.status)


class CampaignJoinSerializer(serializers.Serializer):
    """Serializer for joining a campaign"""
    
    campaign_id = serializers.UUIDField()
    
    def validate_campaign_id(self, value):
        """Validate that campaign exists and can be joined"""
        try:
            campaign = Campaign.objects.get(id=value)
        except Campaign.DoesNotExist:
            raise serializers.ValidationError("Campaign not found")
        
        # Check if campaign is active and accepting riders
        if campaign.status != 'active':
            raise serializers.ValidationError("Campaign is not active")
        
        if not campaign.is_active:
            raise serializers.ValidationError("Campaign is not currently running")
        
        # Check if campaign has available spots
        current_riders = campaign.assigned_riders.filter(
            campaignriderassignment__status__in=['assigned', 'accepted', 'active']
        ).count()
        
        if current_riders >= campaign.required_riders:
            raise serializers.ValidationError("Campaign is full")
        
        return value
    
    def validate(self, attrs):
        """Additional validation"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")
        
        # Check if user has a rider profile
        if not hasattr(request.user, 'rider_profile'):
            raise serializers.ValidationError("Rider profile required")
        
        rider = request.user.rider_profile
        
        # Check if rider is eligible
        if rider.status != 'active':
            raise serializers.ValidationError("Rider account must be active")
        
        if not rider.is_available:
            raise serializers.ValidationError("Rider is not available")
        
        # Check if rider can accept more campaigns
        if not rider.can_accept_campaign:
            raise serializers.ValidationError("Rider has reached maximum concurrent campaigns")
        
        # Check if rider is already in this campaign
        campaign_id = attrs['campaign_id']
        existing_assignment = CampaignRiderAssignment.objects.filter(
            campaign_id=campaign_id,
            rider=rider,
            status__in=['assigned', 'accepted', 'active']
        ).exists()
        
        if existing_assignment:
            raise serializers.ValidationError("Rider is already assigned to this campaign")
        
        return attrs


class CampaignRiderAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for campaign-rider assignments"""
    
    campaign = CampaignSerializer(read_only=True)
    rider_name = serializers.CharField(source='rider.user.get_full_name', read_only=True)
    rider_id = serializers.CharField(source='rider.rider_id', read_only=True)
    
    class Meta:
        model = CampaignRiderAssignment
        fields = [
            'id', 'campaign', 'rider_name', 'rider_id', 'status',
            'assigned_at', 'accepted_at', 'started_at', 'completed_at',
            'verification_count', 'compliance_score', 'distance_covered',
            'amount_earned', 'payment_status'
        ]
        read_only_fields = ['id', 'assigned_at', 'accepted_at', 'started_at', 'completed_at']


class MyCampaignsSerializer(serializers.ModelSerializer):
    """Serializer for rider's active campaigns"""
    
    assignment = serializers.SerializerMethodField('get_assignment')
    client_name = serializers.CharField(source='client.name', read_only=True)
    agency_name = serializers.CharField(source='agency.name', read_only=True)
    days_remaining = serializers.SerializerMethodField('get_days_remaining')
    
    class Meta:
        model = Campaign
        fields = [
            'id', 'name', 'description', 'campaign_type', 'status',
            'client_name', 'agency_name', 'start_date', 'end_date',
            'platform_rate', 'target_cities', 'verification_frequency',
            'days_remaining', 'assignment', 'sticker_design'
        ]
    
    def get_assignment(self, obj):
        """Get rider's assignment details for this campaign"""
        request = self.context.get('request')
        if request and hasattr(request.user, 'rider_profile'):
            try:
                assignment = CampaignRiderAssignment.objects.get(
                    campaign=obj,
                    rider=request.user.rider_profile
                )
                return {
                    'status': assignment.status,
                    'assigned_at': assignment.assigned_at,
                    'accepted_at': assignment.accepted_at,
                    'verification_count': assignment.verification_count,
                    'compliance_score': float(assignment.compliance_score),
                    'amount_earned': float(assignment.amount_earned)
                }
            except CampaignRiderAssignment.DoesNotExist:
                return None
        return None
    
    def get_days_remaining(self, obj):
        """Calculate days remaining in campaign"""
        if obj.end_date:
            now = timezone.now()
            if obj.end_date > now:
                return (obj.end_date - now).days
        return 0