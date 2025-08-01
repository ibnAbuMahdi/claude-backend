from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import Distance
from datetime import datetime, timedelta
from apps.riders.models import Rider
from apps.campaigns.models import CampaignGeofence
from .models import (
    LocationRecord, GeofenceEntry, RiderSession, 
    EarningsCalculation, LocationSyncBatch, DailyTrackingSummary
)
from .serializers import (
    LocationSyncRequestSerializer, LocationSyncResponseSerializer,
    LocationRecordSerializer, GeofenceEntrySerializer, RiderSessionSerializer,
    EarningsCalculationSerializer, EarningsRequestSerializer, TrackingStatsSerializer,
    DailyTrackingSummarySerializer, LocationSyncBatchSerializer
)
from .services import LocationProcessor, EarningsCalculator


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_locations(request):
    """
    Sync location data from mobile app in batches
    Handles offline queue processing and geofence detection
    """
    
    # Get rider from authenticated user
    try:
        rider = request.user.rider_profile
    except:
        return Response(
            {'error': 'User is not a rider'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    serializer = LocationSyncRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    batch_data = serializer.validated_data
    
    try:
        with transaction.atomic():
            # Create sync batch record
            sync_batch = LocationSyncBatch.objects.create(
                rider=rider,
                batch_id=batch_data['batch_id'],
                total_records=len(batch_data['locations']),
                batch_created_at=batch_data['batch_created_at']
            )
            
            # Process locations
            sync_batch.start_processing()
            processor = LocationProcessor(rider, sync_batch)
            
            processed_count = 0
            failed_count = 0
            errors = []
            
            for location_data in batch_data['locations']:
                try:
                    # Check for duplicate mobile_id
                    if LocationRecord.objects.filter(mobile_id=location_data['mobile_id']).exists():
                        continue
                    
                    # Create location record
                    location_record = LocationRecord.objects.create(
                        mobile_id=location_data['mobile_id'],
                        rider=rider,
                        campaign_id=location_data.get('campaign_id'),
                        location=Point(location_data['longitude'], location_data['latitude']),
                        accuracy=location_data['accuracy'],
                        speed=location_data.get('speed'),
                        heading=location_data.get('heading'),
                        altitude=location_data.get('altitude'),
                        recorded_at=location_data['recorded_at'],
                        is_working=location_data.get('is_working', True),
                        metadata=location_data.get('metadata', {})
                    )
                    
                    # Process for geofence events and earnings
                    processor.process_location(location_record)
                    location_record.mark_processed()
                    processed_count += 1
                    
                except Exception as e:
                    failed_count += 1
                    error_info = {
                        'mobile_id': location_data.get('mobile_id'),
                        'error': str(e)
                    }
                    errors.append(error_info)
                    sync_batch.add_error(error_info)
            
            # Update batch status
            sync_batch.processed_records = processed_count
            sync_batch.failed_records = failed_count
            sync_batch.complete_processing()
            
            # Return response
            response_data = {
                'batch_id': sync_batch.batch_id,
                'status': sync_batch.status,
                'processed_count': processed_count,
                'failed_count': failed_count
            }
            
            if errors:
                response_data['errors'] = errors
            
            response_serializer = LocationSyncResponseSerializer(response_data)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
            
    except Exception as e:
        return Response(
            {'error': f'Batch processing failed: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def calculate_earnings(request):
    """
    Calculate earnings for a specific session or period
    Called from mobile app when rider completes work
    """
    
    try:
        rider = request.user.rider_profile
    except:
        return Response(
            {'error': 'User is not a rider'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    serializer = EarningsRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    
    try:
        # Get geofence
        geofence = get_object_or_404(CampaignGeofence, id=data['geofence_id'])
        
        # Calculate earnings
        calculator = EarningsCalculator(rider, geofence)
        earnings = calculator.calculate_earnings(
            earnings_type=data['earnings_type'],
            distance_km=data['distance_km'],
            duration_hours=data['duration_hours'],
            verifications_completed=data['verifications_completed'],
            earned_at=data['earned_at'],
            mobile_id=data['mobile_id'],
            metadata=data['metadata']
        )
        
        serializer = EarningsCalculationSerializer(earnings)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': f'Earnings calculation failed: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rider_tracking_stats(request):
    """
    Get tracking statistics for authenticated rider
    Used by mobile app for dashboard display
    """
    
    try:
        rider = request.user.rider_profile
    except:
        return Response(
            {'error': 'User is not a rider'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    
    # Calculate stats
    today_summary = DailyTrackingSummary.objects.filter(rider=rider, date=today).first()
    week_summaries = DailyTrackingSummary.objects.filter(
        rider=rider, 
        date__gte=week_start, 
        date__lte=today
    )
    month_summaries = DailyTrackingSummary.objects.filter(
        rider=rider, 
        date__gte=month_start, 
        date__lte=today
    )
    
    # Get active geofences
    active_assignments = rider.geofence_assignments.filter(status='active')
    active_geofences = [assignment.campaign_geofence.name for assignment in active_assignments]
    
    # Pending sync count
    pending_sync = LocationRecord.objects.filter(
        rider=rider, 
        sync_status='pending'
    ).count()
    
    # Last sync
    last_sync_batch = LocationSyncBatch.objects.filter(rider=rider).first()
    last_sync = last_sync_batch.received_at if last_sync_batch else None
    
    stats = {
        'today_distance': today_summary.total_distance_km if today_summary else 0,
        'today_earnings': today_summary.total_earnings if today_summary else 0,
        'today_sessions': today_summary.total_sessions if today_summary else 0,
        'week_distance': sum(s.total_distance_km for s in week_summaries),
        'week_earnings': sum(s.total_earnings for s in week_summaries),
        'month_distance': sum(s.total_distance_km for s in month_summaries),
        'month_earnings': sum(s.total_earnings for s in month_summaries),
        'active_geofences': active_geofences,
        'pending_sync_count': pending_sync,
        'last_sync': last_sync
    }
    
    serializer = TrackingStatsSerializer(stats)
    return Response(serializer.data)


class LocationRecordListView(generics.ListCreateAPIView):
    """
    List and create location records
    Used for debugging and manual location entry
    """
    
    serializer_class = LocationRecordSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        try:
            rider = self.request.user.rider_profile
            return LocationRecord.objects.filter(rider=rider)
        except:
            return LocationRecord.objects.none()
    
    def perform_create(self, serializer):
        rider = self.request.user.rider_profile
        serializer.save(rider=rider)


class GeofenceEntryListView(generics.ListAPIView):
    """
    List geofence entry/exit events for rider
    """
    
    serializer_class = GeofenceEntrySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        try:
            rider = self.request.user.rider_profile
            return GeofenceEntry.objects.filter(rider=rider)
        except:
            return GeofenceEntry.objects.none()


class RiderSessionListView(generics.ListAPIView):
    """
    List rider work sessions
    """
    
    serializer_class = RiderSessionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        try:
            rider = self.request.user.rider_profile
            return RiderSession.objects.filter(rider=rider)
        except:
            return RiderSession.objects.none()


class EarningsCalculationListView(generics.ListAPIView):
    """
    List earnings calculations for rider
    """
    
    serializer_class = EarningsCalculationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        try:
            rider = self.request.user.rider_profile
            return EarningsCalculation.objects.filter(rider=rider)
        except:
            return EarningsCalculation.objects.none()


class DailyTrackingSummaryListView(generics.ListAPIView):
    """
    List daily tracking summaries for rider
    """
    
    serializer_class = DailyTrackingSummarySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        try:
            rider = self.request.user.rider_profile
            return DailyTrackingSummary.objects.filter(rider=rider)
        except:
            return DailyTrackingSummary.objects.none()


class LocationSyncBatchListView(generics.ListAPIView):
    """
    List sync batches for rider
    Used for debugging sync issues
    """
    
    serializer_class = LocationSyncBatchSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        try:
            rider = self.request.user.rider_profile
            return LocationSyncBatch.objects.filter(rider=rider)
        except:
            return LocationSyncBatch.objects.none()
