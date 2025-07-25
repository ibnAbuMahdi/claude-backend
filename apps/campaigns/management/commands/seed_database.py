from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Polygon
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import random

from apps.accounts.models import User
from apps.agencies.models import Agency, AgencyClient
from apps.riders.models import Rider
from apps.campaigns.models import Campaign, CampaignGeofence


class Command(BaseCommand):
    help = 'Seed the database with sample campaigns and related data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing seed data before creating new data',
        )

    def handle(self, *args, **options):
        self.stdout.write('Starting database seeding...')
        
        if options['clear']:
            self.clear_existing_data()
        
        # Create users
        self.create_users()
        
        # Create agencies and clients
        self.create_agencies()
        
        # Create riders
        self.create_riders()
        
        # Create campaigns with geofences
        self.create_campaigns()
        
        self.stdout.write(
            self.style.SUCCESS('Successfully seeded database with sample data!')
        )

    def clear_existing_data(self):
        self.stdout.write('Clearing existing seed data...')
        
        # Delete campaigns first (to avoid FK constraints)
        Campaign.objects.filter(name__in=[
            'TechCorp SmartPhone Launch',
            'Fresh Foods Healthy Living Campaign', 
            'Fashion Forward Summer Collection'
        ]).delete()
        
        # Delete users
        User.objects.filter(username__startswith='agency_admin_').delete()
        User.objects.filter(username__startswith='rider_').delete()
        
        # Delete agencies
        Agency.objects.filter(subdomain__in=['creativehub', 'brandforce', 'mediamasters']).delete()
        
        self.stdout.write('✓ Cleared existing seed data')

    def create_users(self):
        self.stdout.write('Creating users...')
        
        # Agency admin users
        self.agency_admin_1 = User.objects.create_user(
            username='agency_admin_1',
            email='admin1@creativehub.com',
            password='password123',
            first_name='John',
            last_name='Smith',
            user_type='agency_admin',
            phone_number='+2348012345671',
            is_verified=True
        )
        
        self.agency_admin_2 = User.objects.create_user(
            username='agency_admin_2',
            email='admin2@brandforce.com',
            password='password123',
            first_name='Sarah',
            last_name='Johnson',
            user_type='agency_admin',
            phone_number='+2348012345672',
            is_verified=True
        )
        
        self.agency_admin_3 = User.objects.create_user(
            username='agency_admin_3',
            email='admin3@mediamasters.com',
            password='password123',
            first_name='Michael',
            last_name='Brown',
            user_type='agency_admin',
            phone_number='+2348012345673',
            is_verified=True
        )
        
        # Rider users
        self.rider_users = []
        for i in range(1, 13):  # Create 12 riders
            rider_user = User.objects.create_user(
                username=f'rider_{i}',
                email=f'rider{i}@example.com',
                password='password123',
                first_name=f'Rider{i}',
                last_name='User',
                user_type='rider',
                phone_number=f'+23480123456{70 + i}',
                is_verified=True
            )
            self.rider_users.append(rider_user)
        
        self.stdout.write('✓ Created users')

    def create_agencies(self):
        self.stdout.write('Creating agencies and clients...')
        
        # Agency 1: Creative Hub
        self.agency_1 = Agency.objects.create(
            name='Creative Hub Agency',
            slug='creative-hub',
            subdomain='creativehub',
            agency_type='full_service',
            email='contact@creativehub.com',
            phone='+2341234567890',
            address='123 Business District, Lagos, Nigeria',
            city='Lagos',
            state='Lagos State',
            subscription_tier='professional',
            is_active=True
        )
        self.agency_admin_1.agency = self.agency_1
        self.agency_admin_1.save()
        
        # Agency 2: Brand Force
        self.agency_2 = Agency.objects.create(
            name='Brand Force Digital',
            slug='brand-force',
            subdomain='brandforce',
            agency_type='digital',
            email='hello@brandforce.com',
            phone='+2341234567891',
            address='456 Tech Avenue, Abuja, Nigeria',
            city='Abuja',
            state='FCT',
            subscription_tier='enterprise',
            is_active=True
        )
        self.agency_admin_2.agency = self.agency_2
        self.agency_admin_2.save()
        
        # Agency 3: Media Masters
        self.agency_3 = Agency.objects.create(
            name='Media Masters Ltd',
            slug='media-masters',
            subdomain='mediamasters',
            agency_type='traditional',
            email='info@mediamasters.com',
            phone='+2341234567892',
            address='789 Marketing Street, Port Harcourt, Nigeria',
            city='Port Harcourt',
            state='Rivers State',
            subscription_tier='starter',
            is_active=True
        )
        self.agency_admin_3.agency = self.agency_3
        self.agency_admin_3.save()
        
        # Create clients for each agency
        self.create_agency_clients()
        
        self.stdout.write('✓ Created agencies and clients')

    def create_agency_clients(self):
        # Clients for Creative Hub
        self.client_1 = AgencyClient.objects.create(
            agency=self.agency_1,
            name='TechCorp Nigeria',
            slug='techcorp-nigeria',
            client_type='technology',
            contact_person='John Tech',
            email='contact@techcorp.ng',
            phone='+2349012345678',
            industry='Technology',
            address='Tech Hub, Victoria Island, Lagos',
            is_active=True
        )
        
        self.client_2 = AgencyClient.objects.create(
            agency=self.agency_1,
            name='Fresh Foods Limited',
            slug='fresh-foods-limited',
            client_type='food_beverage',
            contact_person='Sarah Fresh',
            email='info@freshfoods.ng',
            phone='+2349012345679',
            industry='Food & Beverage',
            address='Industrial Estate, Ikeja, Lagos',
            is_active=True
        )
        
        # Clients for Brand Force
        self.client_3 = AgencyClient.objects.create(
            agency=self.agency_2,
            name='Fashion Forward',
            slug='fashion-forward',
            client_type='fashion',
            contact_person='Mike Fashion',
            email='hello@fashionforward.ng',
            phone='+2349012345680',
            industry='Fashion',
            address='Fashion District, Abuja',
            is_active=True
        )
        
        # Client for Media Masters
        self.client_4 = AgencyClient.objects.create(
            agency=self.agency_3,
            name='AutoParts Plus',
            slug='autoparts-plus',
            client_type='automotive',
            contact_person='David Auto',
            email='sales@autopartsplus.ng',
            phone='+2349012345681',
            industry='Automotive',
            address='Industrial Layout, Port Harcourt',
            is_active=True
        )

    def create_riders(self):
        self.stdout.write('Creating riders...')
        
        self.riders = []
        cities = ['Lagos', 'Abuja', 'Port Harcourt', 'Kano']
        states = ['Lagos State', 'FCT', 'Rivers State', 'Kano State']
        
        for i, user in enumerate(self.rider_users):
            city = cities[i % len(cities)]
            state = states[i % len(states)]
            
            rider = Rider.objects.create(
                user=user,
                rider_id=f'STK-R-{1000 + i}',
                date_of_birth=timezone.now().date() - timedelta(days=random.randint(7300, 18250)),  # 20-50 years
                gender=random.choice(['male', 'female']),
                phone_number=user.phone_number,
                emergency_contact_name=f'Emergency Contact {i+1}',
                emergency_contact_phone=f'+23480987654{20 + i}',
                address=f'{i+10} Rider Street, {city}',
                city=city,
                state=state,
                status='active',
                verification_status='verified',
                tricycle_registration=f'AB{123 + i}CD',
                tricycle_color='Yellow',
                tricycle_model='TVS King',
                tricycle_year=2020 + (i % 4),
                rating=Decimal(str(round(random.uniform(4.0, 5.0), 2))),
                total_earnings=Decimal(str(random.randint(50000, 200000))),
                total_campaigns=random.randint(5, 20),
                passport_photo='riders/photos/default.jpg',
                id_document='riders/documents/default.jpg'
            )
            self.riders.append(rider)
        
        self.stdout.write('✓ Created riders')

    def create_campaigns(self):
        self.stdout.write('Creating campaigns with geofences...')
        
        now = timezone.now()
        
        # Campaign 1: TechCorp Product Launch
        campaign_1 = Campaign.objects.create(
            agency=self.agency_1,
            client=self.client_1,
            created_by=self.agency_admin_1,
            name='TechCorp SmartPhone Launch',
            description='Launch campaign for the new TechCorp SmartPhone targeting tech-savvy millennials in Lagos business districts.',
            campaign_type='product_launch',
            status='active',
            start_date=now - timedelta(days=5),
            end_date=now + timedelta(days=25),
            target_audience='Tech professionals, millennials aged 25-40',
            marketing_objectives='Generate awareness for new smartphone, drive traffic to retail stores',
            required_riders=8,
            platform_rate=Decimal('250.00'),
            agency_rate=Decimal('300.00'),
            total_budget=Decimal('500000.00'),
            target_impressions=100000,
            verification_frequency=4,
            tags=['technology', 'smartphone', 'product_launch']
        )
        
        # Geofences for Campaign 1
        self.create_geofences_for_campaign(campaign_1, [
            {
                'name': 'Victoria Island Business District',
                'description': 'High-traffic business area with tech companies',
                'priority': 1,
                'center_lat': 6.4281,
                'center_lng': 3.4219,
                'radius': 2000,
                'budget': Decimal('200000.00'),
                'max_riders': 3,
                'rate_per_km': Decimal('300.00'),
                'area_type': 'commercial',
                'is_high_priority': True
            },
            {
                'name': 'Ikeja Computer Village',
                'description': 'Major electronics and tech hub',
                'priority': 2,
                'center_lat': 6.6018,
                'center_lng': 3.3515,
                'radius': 1500,
                'budget': Decimal('180000.00'),
                'max_riders': 3,
                'rate_per_km': Decimal('280.00'),
                'area_type': 'commercial',
                'is_high_priority': True
            },
            {
                'name': 'Lekki Phase 1',
                'description': 'Upscale residential area with high purchasing power',
                'priority': 3,
                'center_lat': 6.4698,
                'center_lng': 3.5852,
                'radius': 1800,
                'budget': Decimal('120000.00'),
                'max_riders': 2,
                'rate_per_km': Decimal('250.00'),
                'area_type': 'residential'
            }
        ])
        
        # Campaign 2: Fresh Foods Brand Awareness
        campaign_2 = Campaign.objects.create(
            agency=self.agency_1,
            client=self.client_2,
            created_by=self.agency_admin_1,
            name='Fresh Foods Healthy Living Campaign',
            description='Brand awareness campaign promoting Fresh Foods organic products and healthy lifestyle choices.',
            campaign_type='brand_awareness',
            status='active',
            start_date=now - timedelta(days=10),
            end_date=now + timedelta(days=20),
            target_audience='Health-conscious families, fitness enthusiasts',
            marketing_objectives='Increase brand recognition, promote healthy eating habits',
            required_riders=6,
            platform_rate=Decimal('200.00'),
            agency_rate=Decimal('250.00'),
            total_budget=Decimal('300000.00'),
            target_impressions=75000,
            verification_frequency=3,
            tags=['food', 'health', 'brand_awareness', 'organic']
        )
        
        # Geofences for Campaign 2
        self.create_geofences_for_campaign(campaign_2, [
            {
                'name': 'Surulere Markets',
                'description': 'Busy market areas with high foot traffic',
                'priority': 1,
                'center_lat': 6.5027,
                'center_lng': 3.3620,
                'radius': 1200,
                'budget': Decimal('120000.00'),
                'max_riders': 2,
                'rate_per_km': Decimal('220.00'),
                'area_type': 'commercial'
            },
            {
                'name': 'Fitness Centers Route',
                'description': 'Route covering major gyms and fitness centers',
                'priority': 2,
                'center_lat': 6.5244,
                'center_lng': 3.3792,
                'radius': 2500,
                'budget': Decimal('100000.00'),
                'max_riders': 2,
                'rate_per_km': Decimal('200.00'),
                'area_type': 'mixed'
            },
            {
                'name': 'Family Residential Areas',
                'description': 'Middle-class residential neighborhoods',
                'priority': 3,
                'center_lat': 6.5355,
                'center_lng': 3.3947,
                'radius': 2000,
                'budget': Decimal('80000.00'),
                'max_riders': 2,
                'rate_per_km': Decimal('180.00'),
                'area_type': 'residential'
            }
        ])
        
        # Campaign 3: Fashion Forward Seasonal Campaign
        campaign_3 = Campaign.objects.create(
            agency=self.agency_2,
            client=self.client_3,
            created_by=self.agency_admin_2,
            name='Fashion Forward Summer Collection',
            description='Seasonal campaign showcasing Fashion Forward\'s latest summer collection targeting young professionals in Abuja.',
            campaign_type='seasonal',
            status='approved',
            start_date=now + timedelta(days=3),
            end_date=now + timedelta(days=35),
            target_audience='Young professionals, fashion enthusiasts aged 20-35',
            marketing_objectives='Drive sales for summer collection, increase brand visibility',
            required_riders=5,
            platform_rate=Decimal('275.00'),
            agency_rate=Decimal('325.00'),
            total_budget=Decimal('400000.00'),
            target_impressions=60000,
            verification_frequency=3,
            tags=['fashion', 'seasonal', 'summer', 'professional']
        )
        
        # Geofences for Campaign 3
        self.create_geofences_for_campaign(campaign_3, [
            {
                'name': 'Abuja Central Business District',
                'description': 'Main business area with office complexes',
                'priority': 1,
                'center_lat': 9.0579,
                'center_lng': 7.4951,
                'radius': 1800,
                'budget': Decimal('180000.00'),
                'max_riders': 2,
                'rate_per_km': Decimal('300.00'),
                'area_type': 'commercial',
                'is_high_priority': True
            },
            {
                'name': 'Maitama Shopping District',
                'description': 'Upscale shopping area with boutiques',
                'priority': 2,
                'center_lat': 9.0765,
                'center_lng': 7.4986,
                'radius': 1500,
                'budget': Decimal('150000.00'),
                'max_riders': 2,
                'rate_per_km': Decimal('280.00'),
                'area_type': 'commercial'
            },
            {
                'name': 'University Areas',
                'description': 'Areas around universities and colleges',
                'priority': 3,
                'center_lat': 9.0415,
                'center_lng': 7.4398,
                'radius': 2200,
                'budget': Decimal('70000.00'),
                'max_riders': 1,
                'rate_per_km': Decimal('250.00'),
                'area_type': 'mixed'
            }
        ])
        
        self.stdout.write('✓ Created 3 campaigns with geofences')

    def create_geofences_for_campaign(self, campaign, geofence_data):
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
            
            CampaignGeofence.objects.create(
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