# Stika Backend

Django backend for the Stika B2B2B tricycle advertising platform. Fully compliant with the `stika-backend-revised.md` plan.

## Features

- **Multi-tenant Architecture**: Agencies get white-label access with subdomains
- **Geospatial Support**: PostGIS for location tracking and route optimization  
- **Computer Vision**: Automated sticker verification system
- **API-First Design**: RESTful APIs + GraphQL for complex queries
- **Background Tasks**: Specialized Celery queues for verification, payments, analytics
- **Defensive Architecture**: Competitive intelligence, exclusive contracts, audit trails
- **OpenAPI Documentation**: Auto-generated API docs with Swagger UI

## Core Models

### User Management
- **User**: Custom user model supporting different user types
- **UserProfile**: Extended profile information

### Agency Management  
- **Agency**: Advertising agencies (primary customers)
- **AgencyClient**: Clients that agencies manage campaigns for
- **AgencyAPIKey**: API access keys for integrations

### Campaign Management
- **Campaign**: Advertising campaigns with geospatial targeting
- **CampaignRiderAssignment**: Rider assignments with performance tracking
- **CampaignMetrics**: Daily aggregated campaign metrics

### Rider Operations
- **Rider**: Tricycle operators who display advertisements
- **RiderLocation**: GPS tracking for route optimization
- **RiderPerformance**: Performance analytics and scoring

### Verification System
- **VerificationRequest**: Computer vision verification with location data

### Fleet Management
- **Fleet**: Fleet owners who manage multiple riders

### Payments
- **Payment**: Transaction processing for the platform

## Setup

1. Copy environment variables:
```bash
cp .env.example .env
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up PostgreSQL with PostGIS:
```sql
CREATE DATABASE stika_db;
CREATE USER stika_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE stika_db TO stika_user;
```

4. Run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

5. Create superuser:
```bash
python manage.py createsuperuser
```

6. Start development server:
```bash
python manage.py runserver
```

## API Endpoints

- `/api/v1/auth/` - Authentication
- `/api/v1/agencies/` - Agency management
- `/api/v1/campaigns/` - Campaign operations  
- `/api/v1/riders/` - Rider management
- `/api/v1/verification/` - Computer vision verification
- `/api/v1/payments/` - Payment processing

## Multi-Tenant Architecture

Agencies access the platform via subdomains:
- `agency1.stika.ng` - White-labeled portal for Agency 1
- `agency2.stika.ng` - White-labeled portal for Agency 2
- `api.stika.ng` - API access for all agencies

The `TenantMiddleware` automatically detects the agency based on subdomain and sets the appropriate context.

## Background Tasks

Celery handles:
- Payment processing
- Report generation
- Notification sending
- Computer vision processing
- Analytics aggregation

Start Celery worker:
```bash
celery -A stika worker -l info
```

## Testing

Run tests:
```bash
python manage.py test
```

## Production Deployment

1. Set `DEBUG=False` in environment
2. Configure proper database credentials
3. Set up Redis for caching and Celery
4. Configure AWS S3 for file storage
5. Set up Sentry for error tracking