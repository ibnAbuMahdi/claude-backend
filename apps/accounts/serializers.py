# apps/accounts/serializers.py
from rest_framework import serializers
from .models import User, UserProfile
from apps.riders.models import Rider

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'phone_number', 'user_type', 'is_verified']
        read_only_fields = ['id', 'user_type', 'is_verified']

class RiderProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    
    # Handle the naming mismatches
    pending_balance = serializers.DecimalField(source='pending_earnings', max_digits=10, decimal_places=2, read_only=True)
    available_balance = serializers.SerializerMethodField()
    average_rating = serializers.DecimalField(source='rating', max_digits=3, decimal_places=2, read_only=True)
    
    # Add computed fields
    has_completed_onboarding = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    is_verified = serializers.SerializerMethodField()
    
    class Meta:
        model = Rider
        fields = [
            'id', 'user', 'rider_id', 'full_name', 'first_name', 'last_name',
            'phone_number', 'status', 'verification_status', 
            'has_completed_onboarding', 'is_active', 'is_verified',
            'rating', 'average_rating', 'compliance_score',
            'total_campaigns', 'total_earnings', 'pending_earnings', 'pending_balance',
            'available_balance', 'is_available', 'current_location', 'created_at'
        ]
        read_only_fields = [
            'id', 'rider_id', 'rating', 'average_rating', 'compliance_score',
            'total_campaigns', 'total_earnings', 'created_at'
        ]
    
    def get_available_balance(self, obj):
        return obj.total_earnings - obj.pending_earnings
    
    def get_has_completed_onboarding(self, obj):
        # Define your onboarding completion logic
        required_fields = [obj.date_of_birth, obj.tricycle_registration]
        return all(field for field in required_fields)
    
    def get_is_active(self, obj):
        return obj.status == 'active'
    
    def get_is_verified(self, obj):
        return obj.verification_status == 'verified'

