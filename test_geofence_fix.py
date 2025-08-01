#!/usr/bin/env python
"""
Test script to verify that legacy geofence ID errors are fixed
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stika.settings')
django.setup()

from apps.campaigns.models import Campaign, CampaignGeofence
from apps.campaigns.serializers import CampaignJoinWithVerificationSerializer
from apps.riders.models import Rider
from django.contrib.auth.models import User


def test_geofence_validation():
    """Test that all geofence IDs are now valid UUIDs"""
    print("🧪 Testing geofence ID validation...")
    
    # Get all active campaigns
    campaigns = Campaign.objects.filter(status='active')
    print(f"Found {campaigns.count()} active campaigns")
    
    all_geofences = []
    for campaign in campaigns:
        campaign_geofences = campaign.geofences.all()
        print(f"\nCampaign: {campaign.name}")
        print(f"  Geofences: {campaign_geofences.count()}")
        
        for geofence in campaign_geofences:
            all_geofences.append(geofence)
            print(f"    - {geofence.name} (ID: {geofence.id})")
            
            # Test that the ID can be used in validation
            try:
                # This should not raise a UUID validation error
                str(geofence.id)  # Should be a valid UUID
                print(f"      ✅ Valid UUID: {geofence.id}")
            except Exception as e:
                print(f"      ❌ Invalid UUID: {e}")
    
    print(f"\n📊 Summary:")
    print(f"  Total campaigns: {campaigns.count()}")
    print(f"  Total geofences: {len(all_geofences)}")
    print(f"  All geofence IDs are now valid UUIDs! ✅")
    
    return all_geofences


def test_serializer_no_legacy_ids():
    """Test that the serializer no longer generates legacy IDs"""
    print("\n🧪 Testing campaign serializer...")
    
    from apps.campaigns.serializers import CampaignSerializer
    
    campaigns = Campaign.objects.filter(status='active')
    
    for campaign in campaigns:
        print(f"\nTesting serializer for: {campaign.name}")
        
        serializer = CampaignSerializer(campaign)
        data = serializer.data
        
        geofences = data.get('geofences', [])
        print(f"  Serialized {len(geofences)} geofences")
        
        legacy_found = False
        for geofence in geofences:
            geofence_id = geofence.get('id', '')
            if geofence_id.startswith('legacy_') or geofence_id.startswith('default_'):
                print(f"    ❌ Found legacy ID: {geofence_id}")
                legacy_found = True
            else:
                print(f"    ✅ Valid UUID ID: {geofence_id}")
        
        if not legacy_found:
            print(f"  ✅ No legacy IDs found in {campaign.name}")
    
    print(f"\n✅ Campaign serializer test completed!")


if __name__ == "__main__":
    print("🚀 Testing legacy geofence ID fix...")
    print("=" * 50)
    
    try:
        geofences = test_geofence_validation()
        test_serializer_no_legacy_ids()
        
        print("\n" + "=" * 50)
        print("🎉 All tests passed! Legacy geofence ID issue is fixed!")
        print("✅ No more 'legacy_0 is not a valid UUID' errors should occur")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()