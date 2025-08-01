#!/usr/bin/env python
"""
Script to create campaigns with geofences and pickup locations for Birnin Kebbi and Kalgo, Kebbi State
"""

import os
import sys
import django

# Setup Django
sys.path.append('/home/ruhullah/Stika/Backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stika.settings')
django.setup()

from django.contrib.gis.geos import Polygon
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from apps.accounts.models import User
from apps.agencies.models import Agency, AgencyClient
from apps.campaigns.models import Campaign, CampaignGeofence, PickupLocation


def create_kebbi_campaigns():
    """Create campaigns for Birnin Kebbi and Kalgo areas"""
    
    print("Starting campaign creation for Kebbi State...")
    
    # Get or create agency and client
    agency = get_or_create_agency()
    client = get_or_create_client(agency)
    admin_user = get_or_create_admin_user(agency)
    
    now = timezone.now()
    
    # Campaign 1: Birnin Kebbi Commercial Campaign
    birnin_kebbi_campaign = Campaign.objects.create(
        agency=agency,
        client=client,
        created_by=admin_user,
        name='Kebbi Commerce Drive - Birnin Kebbi',
        description='Commercial advertising campaign targeting business districts and markets in Birnin Kebbi, the capital of Kebbi State.',
        campaign_type='brand_awareness',
        status='active',
        start_date=now,
        end_date=now + timedelta(days=30),
        target_audience='Local businesses, traders, government workers',
        marketing_objectives='Increase brand visibility in Kebbi State capital, drive local business engagement',
        required_riders=6,
        platform_rate=Decimal('180.00'),
        agency_rate=Decimal('220.00'),
        total_budget=Decimal('250000.00'),
        target_impressions=40000,
        verification_frequency=3,
        tags=['kebbi', 'birnin_kebbi', 'commercial', 'local_business']
    )
    
    # Geofences for Birnin Kebbi
    birnin_kebbi_geofences = [
        {
            'name': 'Birnin Kebbi Central Market',
            'description': 'Main commercial market in Birnin Kebbi with high foot traffic',
            'priority': 1,
            'center_lat': 12.4539,
            'center_lng': 4.1975,
            'radius': 800,
            'budget': Decimal('80000.00'),
            'max_riders': 2,
            'rate_per_km': Decimal('200.00'),
            'area_type': 'commercial',
            'is_high_priority': True
        },
        {
            'name': 'Government Secretariat Area',
            'description': 'Government offices and administrative buildings',
            'priority': 2,
            'center_lat': 12.4560,
            'center_lng': 4.1990,
            'radius': 1000,
            'budget': Decimal('90000.00'),
            'max_riders': 2,
            'rate_per_km': Decimal('190.00'),
            'area_type': 'government',
            'is_high_priority': True
        },
        {
            'name': 'Birnin Kebbi Banking District',
            'description': 'Area with major banks and financial institutions',
            'priority': 3,
            'center_lat': 12.4520,
            'center_lng': 4.1950,
            'radius': 600,
            'budget': Decimal('50000.00'),
            'max_riders': 1,
            'rate_per_km': Decimal('180.00'),
            'area_type': 'commercial'
        },
        {
            'name': 'Residential Quarters',
            'description': 'Main residential areas in Birnin Kebbi',
            'priority': 4,
            'center_lat': 12.4580,
            'center_lng': 4.2020,
            'radius': 1200,
            'budget': Decimal('30000.00'),
            'max_riders': 1,
            'rate_per_km': Decimal('160.00'),
            'area_type': 'residential'
        }
    ]
    
    create_geofences_for_campaign(birnin_kebbi_campaign, birnin_kebbi_geofences)
    
    # Campaign 2: Kalgo Agricultural Campaign
    kalgo_campaign = Campaign.objects.create(
        agency=agency,
        client=client,
        created_by=admin_user,
        name='Kalgo Agricultural Hub Campaign',
        description='Campaign targeting the agricultural hub of Kalgo, focusing on farmers, agricultural markets, and rural development.',
        campaign_type='promotional',
        status='active',
        start_date=now,
        end_date=now + timedelta(days=25),
        target_audience='Farmers, agricultural traders, rural communities',
        marketing_objectives='Promote agricultural products and services, reach rural markets',
        required_riders=4,
        platform_rate=Decimal('150.00'),
        agency_rate=Decimal('190.00'),
        total_budget=Decimal('180000.00'),
        target_impressions=25000,
        verification_frequency=2,
        tags=['kebbi', 'kalgo', 'agriculture', 'rural', 'farming']
    )
    
    # Geofences for Kalgo
    kalgo_geofences = [
        {
            'name': 'Kalgo Central Market',
            'description': 'Main market serving agricultural communities',
            'priority': 1,
            'center_lat': 12.3167,
            'center_lng': 4.1833,
            'radius': 700,
            'budget': Decimal('70000.00'),
            'max_riders': 2,
            'rate_per_km': Decimal('170.00'),
            'area_type': 'commercial',
            'is_high_priority': True
        },
        {
            'name': 'Agricultural Processing Zone',
            'description': 'Area with rice mills and agricultural processing facilities',
            'priority': 2,
            'center_lat': 12.3200,
            'center_lng': 4.1850,
            'radius': 1000,
            'budget': Decimal('60000.00'),
            'max_riders': 1,
            'rate_per_km': Decimal('160.00'),
            'area_type': 'industrial'
        },
        {
            'name': 'Farming Communities Route',
            'description': 'Route covering major farming settlements',
            'priority': 3,
            'center_lat': 12.3100,
            'center_lng': 4.1800,
            'radius': 1500,
            'budget': Decimal('50000.00'),
            'max_riders': 1,
            'rate_per_km': Decimal('140.00'),
            'area_type': 'rural'
        }
    ]
    
    create_geofences_for_campaign(kalgo_campaign, kalgo_geofences)
    
    # Create pickup locations for both campaigns
    create_pickup_locations(birnin_kebbi_campaign, kalgo_campaign)
    
    print(f"✅ Successfully created campaigns:")
    print(f"   - {birnin_kebbi_campaign.name} (ID: {birnin_kebbi_campaign.id})")
    print(f"   - {kalgo_campaign.name} (ID: {kalgo_campaign.id})")
    print(f"✅ Created {CampaignGeofence.objects.filter(campaign__in=[birnin_kebbi_campaign, kalgo_campaign]).count()} geofences")
    print(f"✅ Created pickup locations for both campaigns")
    
    return birnin_kebbi_campaign, kalgo_campaign


def get_or_create_agency():
    """Get or create Kebbi agency"""
    agency, created = Agency.objects.get_or_create(
        subdomain='kebbi-promotions',
        defaults={
            'name': 'Kebbi State Promotions Agency',
            'slug': 'kebbi-promotions',
            'agency_type': 'regional',
            'email': 'info@kebbipromotions.ng',
            'phone': '+2348123456789',
            'address': 'Government House Road, Birnin Kebbi, Kebbi State',
            'city': 'Birnin Kebbi',
            'state': 'Kebbi State',
            'subscription_tier': 'professional',
            'is_active': True
        }
    )
    
    if created:
        print(f"✅ Created new agency: {agency.name}")
    else:
        print(f"✅ Using existing agency: {agency.name}")
    
    return agency


def get_or_create_client(agency):
    """Get or create client for the agency"""
    client, created = AgencyClient.objects.get_or_create(
        agency=agency,
        slug='kebbi-local-business',
        defaults={
            'name': 'Kebbi Local Business Initiative',
            'client_type': 'government',
            'contact_person': 'Malam Ibrahim Kebbi',
            'email': 'ibrahim@kebbibusiness.ng',
            'phone': '+2348123456790',
            'industry': 'Local Development',
            'address': 'Trade Center, Birnin Kebbi, Kebbi State',
            'is_active': True
        }
    )
    
    if created:
        print(f"✅ Created new client: {client.name}")
    else:
        print(f"✅ Using existing client: {client.name}")
    
    return client


def get_or_create_admin_user(agency):
    """Get or create admin user for the agency"""
    user, created = User.objects.get_or_create(
        username='kebbi_admin',
        defaults={
            'email': 'admin@kebbipromotions.ng',
            'first_name': 'Kebbi',
            'last_name': 'Administrator',
            'user_type': 'agency_admin',
            'phone_number': '+2348123456789',
            'is_verified': True,
            'agency': agency
        }
    )
    
    if created:
        user.set_password('kebbi123')
        user.save()
        print(f"✅ Created new admin user: {user.username}")
    else:
        print(f"✅ Using existing admin user: {user.username}")
    
    return user


def create_geofences_for_campaign(campaign, geofence_data):
    """Helper method to create geofences for a campaign"""
    for data in geofence_data:
        # Create a simple circular polygon for the geofence
        lat = float(data['center_lat'])
        lng = float(data['center_lng'])
        radius_deg = data['radius'] / 111000  # Rough conversion from meters to degrees
        
        # Create a simple square polygon around the center point
        min_lat = lat - radius_deg
        max_lat = lat + radius_deg
        min_lng = lng - radius_deg
        max_lng = lng + radius_deg
        
        polygon = Polygon.from_bbox((min_lng, min_lat, max_lng, max_lat))
        
        geofence = CampaignGeofence.objects.create(
            campaign=campaign,
            name=data['name'],
            description=data['description'],
            priority=data['priority'],
            geofence_data=polygon,
            center_latitude=Decimal(str(data['center_lat'])),
            center_longitude=Decimal(str(data['center_lng'])),
            radius_meters=data['radius'],
            budget=data['budget'],
            spent=Decimal('0.00'),
            rate_type='per_km',
            rate_per_km=data['rate_per_km'],
            rate_per_hour=Decimal('0.00'),
            fixed_daily_rate=Decimal('0.00'),
            start_date=campaign.start_date,
            end_date=campaign.end_date,
            max_riders=data['max_riders'],
            current_riders=0,
            min_riders=1,
            target_coverage_hours=8,
            verification_frequency=campaign.verification_frequency,
            status='active',
            is_high_priority=data.get('is_high_priority', False),
            area_type=data.get('area_type', ''),
            target_demographics={}
        )
        
        print(f"   ✅ Created geofence: {geofence.name}")


def create_pickup_locations(birnin_kebbi_campaign, kalgo_campaign):
    """Create pickup locations for both campaigns"""
    
    # Pickup locations for Birnin Kebbi campaign
    birnin_kebbi_geofences = birnin_kebbi_campaign.geofences.all()
    
    # Market geofence pickup location
    market_geofence = birnin_kebbi_geofences.filter(name='Birnin Kebbi Central Market').first()
    if market_geofence:
        PickupLocation.objects.create(
            geofence=market_geofence,
            contact_name='Alhaji Usman Market',
            contact_phone='+2348111111111',
            address='Shop 45, Central Market, Birnin Kebbi',
            landmark='Near the main gate of Central Market',
            pickup_instructions='Ask for Alhaji Usman at the phone accessories section. Bring your rider ID.',
            operating_hours={
                'monday': '08:00-18:00',
                'tuesday': '08:00-18:00',
                'wednesday': '08:00-18:00',
                'thursday': '08:00-18:00',
                'friday': '08:00-12:00',
                'saturday': '08:00-18:00',
                'sunday': 'Closed'
            },
            is_active=True,
            notes='Main pickup point for market area. Has secure storage for stickers.'
        )
    
    # Government area pickup location
    gov_geofence = birnin_kebbi_geofences.filter(name='Government Secretariat Area').first()
    if gov_geofence:
        PickupLocation.objects.create(
            geofence=gov_geofence,
            contact_name='Ibrahim Government Liaison',
            contact_phone='+2348111111112',
            address='Block A, Government Secretariat, Birnin Kebbi',
            landmark='Near the main entrance of Government Secretariat',
            pickup_instructions='Go to Block A reception desk and ask for Ibrahim. Show your rider verification.',
            operating_hours={
                'monday': '09:00-16:00',
                'tuesday': '09:00-16:00',
                'wednesday': '09:00-16:00',
                'thursday': '09:00-16:00',
                'friday': '09:00-12:00',
                'saturday': 'Closed',
                'sunday': 'Closed'
            },
            is_active=True,
            notes='Official government pickup point. Requires ID verification.'
        )
    
    # Banking district pickup location
    bank_geofence = birnin_kebbi_geofences.filter(name='Birnin Kebbi Banking District').first()
    if bank_geofence:
        PickupLocation.objects.create(
            geofence=bank_geofence,
            contact_name='Fatima Banking Hub',
            contact_phone='+2348111111113',
            address='First Bank Building, Banking Street, Birnin Kebbi',
            landmark='Opposite UBA Bank',
            pickup_instructions='Enter First Bank building and ask security for Fatima at the business center.',
            operating_hours={
                'monday': '09:00-15:00',
                'tuesday': '09:00-15:00',
                'wednesday': '09:00-15:00',
                'thursday': '09:00-15:00',
                'friday': '09:00-12:00',
                'saturday': 'Closed',
                'sunday': 'Closed'
            },
            is_active=True,
            notes='Located in banking district. Best access during banking hours.'
        )
    
    # Pickup locations for Kalgo campaign
    kalgo_geofences = kalgo_campaign.geofences.all()
    
    # Kalgo market pickup location
    kalgo_market_geofence = kalgo_geofences.filter(name='Kalgo Central Market').first()
    if kalgo_market_geofence:
        PickupLocation.objects.create(
            geofence=kalgo_market_geofence,
            contact_name='Malam Sani Kalgo',
            contact_phone='+2348111111114',
            address='Grain Section, Kalgo Central Market',
            landmark='Near the rice sellers area',
            pickup_instructions='Look for Malam Sani at the grain section. He wears a blue cap usually.',
            operating_hours={
                'monday': '07:00-17:00',
                'tuesday': '07:00-17:00',
                'wednesday': '07:00-17:00',
                'thursday': '07:00-17:00',
                'friday': '07:00-12:00',
                'saturday': '07:00-17:00',
                'sunday': 'Closed'
            },
            is_active=True,
            notes='Main pickup point for agricultural area. Familiar with farming community.'
        )
    
    # Agricultural processing zone pickup location
    agric_geofence = kalgo_geofences.filter(name='Agricultural Processing Zone').first()
    if agric_geofence:
        PickupLocation.objects.create(
            geofence=agric_geofence,
            contact_name='Hauwa Rice Mill',
            contact_phone='+2348111111115',
            address='Kalgo Rice Mill Complex, Processing Zone',
            landmark='Near the main rice mill entrance',
            pickup_instructions='Ask for Hauwa at the mill office. She manages the community outreach.',
            operating_hours={
                'monday': '08:00-16:00',
                'tuesday': '08:00-16:00',
                'wednesday': '08:00-16:00',
                'thursday': '08:00-16:00',
                'friday': '08:00-12:00',
                'saturday': '08:00-14:00',
                'sunday': 'Closed'
            },
            is_active=True,
            notes='Located at rice mill. Good connection with farming communities.'
        )
    
    print(f"✅ Created pickup locations for both campaigns")


if __name__ == '__main__':
    create_kebbi_campaigns()