"""
Management command to create proper CampaignGeofence records for campaigns 
that are currently using legacy/default geofence IDs in the serializer.

This fixes the "legacy_0" is not a valid UUID error by creating actual 
CampaignGeofence database records with proper UUIDs.
"""

from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point, Polygon
from django.utils import timezone
from decimal import Decimal
import uuid

from apps.campaigns.models import Campaign, CampaignGeofence, PickupLocation


class Command(BaseCommand):
    help = 'Create proper CampaignGeofence records for campaigns using legacy/default geofence IDs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating records',
        )
        parser.add_argument(
            '--campaign-id',
            type=str,
            help='Process only a specific campaign by ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        campaign_id = options.get('campaign_id')
        
        self.stdout.write(self.style.SUCCESS('Starting legacy geofence fix...'))
        
        # Get campaigns that need geofence records created
        campaigns_query = Campaign.objects.filter(status='active')
        if campaign_id:
            campaigns_query = campaigns_query.filter(id=campaign_id)
            
        campaigns_without_geofences = []
        
        for campaign in campaigns_query:
            # Check if campaign has any actual CampaignGeofence records
            geofence_count = campaign.geofences.count()
            if geofence_count == 0:
                campaigns_without_geofences.append(campaign)
                
        self.stdout.write(
            f'Found {len(campaigns_without_geofences)} campaigns without proper geofence records'
        )
        
        if not campaigns_without_geofences:
            self.stdout.write(self.style.SUCCESS('No campaigns need fixing!'))
            return
            
        created_count = 0
        
        for campaign in campaigns_without_geofences:
            self.stdout.write(f'\nProcessing campaign: {campaign.name} (ID: {campaign.id})')
            
            # Create geofences based on campaign target_areas or default locations
            geofences_to_create = self._get_geofences_for_campaign(campaign)
            
            for geofence_data in geofences_to_create:
                if dry_run:
                    self.stdout.write(
                        f'  [DRY RUN] Would create geofence: {geofence_data["name"]} '
                        f'at ({geofence_data["center_latitude"]}, {geofence_data["center_longitude"]})'
                    )
                else:
                    # Create the actual CampaignGeofence record
                    geofence = self._create_geofence(campaign, geofence_data)
                    
                    # Create pickup locations for this geofence
                    pickup_locations = self._create_pickup_locations(geofence, geofence_data)
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  ✓ Created geofence: {geofence.name} (ID: {geofence.id}) '
                            f'with {len(pickup_locations)} pickup locations'
                        )
                    )
                    created_count += 1
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'\n[DRY RUN] Would create {len([g for c in campaigns_without_geofences for g in self._get_geofences_for_campaign(c)])} geofence records'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'\n✓ Successfully created {created_count} geofence records!')
            )
            self.stdout.write(
                self.style.SUCCESS('Legacy geofence IDs have been fixed!')
            )

    def _get_geofences_for_campaign(self, campaign):
        """Get geofence data that should be created for this campaign"""
        geofences = []
        
        # Try to use target_areas if available
        if campaign.target_areas and len(campaign.target_areas) > 0:
            # Use existing target_areas polygons
            area_names = {
                0: {"name": "Victoria Island", "radius": 3000},
                1: {"name": "Ikeja", "radius": 4000}, 
                2: {"name": "Surulere", "radius": 3500},
                3: {"name": "Lagos Island", "radius": 2000},
            }
            
            budget_per_geofence = float(campaign.total_budget) / len(campaign.target_areas)
            riders_per_geofence = max(1, campaign.required_riders // len(campaign.target_areas))
            
            for i, polygon in enumerate(campaign.target_areas):
                if i < len(area_names):
                    area_info = area_names[i]
                    centroid = polygon.centroid
                    
                    geofences.append({
                        "name": area_info["name"],
                        "center_latitude": centroid.y,
                        "center_longitude": centroid.x,
                        "radius_meters": area_info["radius"],
                        "budget": budget_per_geofence,
                        "max_riders": riders_per_geofence,
                        "priority": i + 1,
                        "polygon": polygon,
                    })
        else:
            # Create default geofences based on budget
            budget = float(campaign.total_budget)
            default_geofences_data = [
                {
                    "name": "Victoria Island",
                    "center_latitude": 6.4269, "center_longitude": 3.4105,
                    "radius_meters": 3000, "priority": 1
                },
                {
                    "name": "Ikeja", 
                    "center_latitude": 6.6018, "center_longitude": 3.3515,
                    "radius_meters": 4000, "priority": 2
                }
            ]
            
            if budget >= 200000:
                default_geofences_data.extend([
                    {
                        "name": "Surulere",
                        "center_latitude": 6.4969, "center_longitude": 3.3603,
                        "radius_meters": 3500, "priority": 3
                    },
                    {
                        "name": "Lagos Island",
                        "center_latitude": 6.4541, "center_longitude": 3.3947,
                        "radius_meters": 2000, "priority": 4
                    }
                ])
            elif budget >= 100000:
                default_geofences_data.append({
                    "name": "Surulere",
                    "center_latitude": 6.4969, "center_longitude": 3.3603,
                    "radius_meters": 3500, "priority": 3
                })
            
            budget_per_geofence = budget / len(default_geofences_data)
            riders_per_geofence = max(1, campaign.required_riders // len(default_geofences_data))
            
            for gf_data in default_geofences_data:
                # Create a simple circular polygon from center and radius
                center = Point(gf_data["center_longitude"], gf_data["center_latitude"])
                
                geofences.append({
                    "name": gf_data["name"],
                    "center_latitude": gf_data["center_latitude"],
                    "center_longitude": gf_data["center_longitude"],
                    "radius_meters": gf_data["radius_meters"],
                    "budget": budget_per_geofence,
                    "max_riders": riders_per_geofence,
                    "priority": gf_data["priority"],
                    "polygon": None,  # Will create from center/radius
                })
        
        return geofences

    def _create_geofence(self, campaign, geofence_data):
        """Create a CampaignGeofence record"""
        
        # Create geofence geometry
        if geofence_data.get("polygon"):
            geofence_geometry = geofence_data["polygon"]
        else:
            # Create circular polygon from center and radius
            center_lon = geofence_data["center_longitude"]
            center_lat = geofence_data["center_latitude"]
            radius_meters = geofence_data["radius_meters"]
            
            # Convert radius from meters to degrees (approximate)
            radius_degrees = radius_meters / 111320.0  # meters per degree at equator
            
            # Create a simple square polygon (for simplicity)
            coords = [
                (center_lon - radius_degrees, center_lat - radius_degrees),
                (center_lon + radius_degrees, center_lat - radius_degrees),
                (center_lon + radius_degrees, center_lat + radius_degrees),
                (center_lon - radius_degrees, center_lat + radius_degrees),
                (center_lon - radius_degrees, center_lat - radius_degrees),  # Close the ring
            ]
            geofence_geometry = Polygon(coords)
        
        # Create the geofence record
        geofence = CampaignGeofence.objects.create(
            campaign=campaign,
            name=geofence_data["name"],
            description=f"Auto-generated geofence for {campaign.name}",
            center_latitude=Decimal(str(geofence_data["center_latitude"])),
            center_longitude=Decimal(str(geofence_data["center_longitude"])),
            radius_meters=geofence_data["radius_meters"],
            geofence_data=geofence_geometry,
            
            # Financial settings
            budget=Decimal(str(geofence_data["budget"])),
            spent=Decimal('0.00'),
            rate_type='per_km',
            rate_per_km=Decimal(str(float(campaign.platform_rate) / 50.0)),  # From serializer logic
            rate_per_hour=Decimal(str(float(campaign.platform_rate) / 8.0)),
            fixed_daily_rate=campaign.platform_rate,
            
            # Date settings
            start_date=campaign.start_date,
            end_date=campaign.end_date,
            
            # Rider settings
            max_riders=geofence_data["max_riders"],
            current_riders=0,
            min_riders=1,
            
            # Priority and status
            priority=geofence_data["priority"],
            status='active',
            is_high_priority=(geofence_data["priority"] == 1),
            
            # Coverage settings
            target_coverage_hours=8,
            verification_frequency=campaign.verification_frequency,
            area_type='mixed',
        )
        
        return geofence

    def _create_pickup_locations(self, geofence, geofence_data):
        """Create default pickup locations for this geofence"""
        pickup_locations = []
        
        # Create a default pickup location at the geofence center
        pickup_location = PickupLocation.objects.create(
            geofence=geofence,  # Direct foreign key assignment
            contact_name=f"{geofence.name} Pickup Point",
            contact_phone="+234-XXX-XXX-XXXX",  # Placeholder
            address=f"{geofence.name}, Lagos, Nigeria",
            landmark=f"Near {geofence.name} area",
            pickup_instructions=f"Contact rider coordinator for pickup at {geofence.name} location",
            operating_hours={
                "monday": "8:00-17:00",
                "tuesday": "8:00-17:00", 
                "wednesday": "8:00-17:00",
                "thursday": "8:00-17:00",
                "friday": "8:00-17:00",
                "saturday": "9:00-15:00",
                "sunday": "Closed"
            },
            is_active=True,
            notes=f"Auto-generated pickup location for {geofence.name} geofence",
        )
        
        pickup_locations.append(pickup_location)
        
        return pickup_locations