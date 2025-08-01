from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db import transaction
from django.contrib.gis.geos import Point
from datetime import timedelta
from django.db.models import Count, Avg, Q
import logging

from .models import VerificationRequest, VerificationCooldown
from .services import VerificationProcessor, CooldownManager
from .serializers import (
    CreateRandomVerificationSerializer,
    SubmitVerificationSerializer,
    VerificationRequestSerializer, 
    PendingVerificationSerializer,
    VerificationStatsSerializer,
    MobileVerificationRequestSerializer
)
from apps.campaigns.models import Campaign, CampaignGeofenceAssignment

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_random_verification(request):
    """
    Create a random verification request initiated by mobile app
    
    POST /api/v1/verifications/create-random/
    
    Expected data:
    {
        "latitude": 6.5244,
        "longitude": 3.3792,
        "accuracy": 5.0,
        "campaign_id": "optional-uuid"
    }
    """
    logger.info(f"=== CREATE RANDOM VERIFICATION ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Data: {request.data}")
    
    try:
        rider = request.user.rider_profile
        
        # Validate request data
        serializer = CreateRandomVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Invalid create verification request: {serializer.errors}")
            return Response({
                'success': False,
                'message': 'Invalid request data',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = serializer.validated_data
        
        # Check cooldown
        can_verify, cooldown_remaining = CooldownManager.check_cooldown(rider, 'random')
        if not can_verify:
            logger.info(f"Rider {rider.rider_id} is in cooldown for {cooldown_remaining} seconds")
            return Response({
                'success': False,
                'message': 'Please wait before requesting another verification',
                'reason': 'cooldown_active',
                'retry_after_seconds': int(cooldown_remaining)
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
        
        # Find rider's active geofence assignments
        rider_location = Point(
            float(validated_data['longitude']),
            float(validated_data['latitude'])
        )
        
        # Get active geofence assignments for this rider
        active_geofence_assignments = CampaignGeofenceAssignment.objects.filter(
            rider=rider,
            status='active',
            campaign_geofence__status='active'
        ).select_related('campaign_geofence__campaign', 'campaign_geofence')
        
        if not active_geofence_assignments.exists():
            logger.info(f"Rider {rider.rider_id} has no active geofence assignments")
            return Response({
                'success': False,
                'message': 'No active geofence assignment found',
                'reason': 'no_active_geofence_assignment'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if rider is within any of their assigned geofences
        assigned_geofence = None
        campaign = None
        
        for assignment in active_geofence_assignments:
            geofence_obj = assignment.campaign_geofence
            if geofence_obj.geofence_data.contains(rider_location):
                assigned_geofence = geofence_obj
                campaign = geofence_obj.campaign
                logger.info(f"Rider {rider.rider_id} is within polygon geofence: {geofence_obj.name}")
                break

	    # Fallback: check circular geofence
            elif (
                geofence_obj.center_latitude is not None and
                geofence_obj.center_longitude is not None and
                geofence_obj.radius_meters is not None
            ):
                logger.info(f"Longitude: {geofence_obj.center_longitude} - Latitude {geofence_obj.center_latitude}")
                center = Point(float(geofence_obj.center_longitude), float(geofence_obj.center_latitude))
                if center.distance(rider_location) * 111320 <= geofence_obj.radius_meters:  # convert meters to kilometers
                    assigned_geofence = geofence_obj
                    campaign = geofence_obj.campaign
                    logger.info(f"Rider {rider.rider_id} is within circular geofence: {geofence_obj.name}")
                    break
        
        if not assigned_geofence or not campaign:
            # Get names of assigned geofences for better error message
            assigned_geofence_names = [a.campaign_geofence.name for a in active_geofence_assignments]
            logger.info(f"Rider {rider.rider_id} is outside assigned geofences: {assigned_geofence_names}")
            return Response({
                'success': False,
                'message': f'You must be within your assigned geofence area to verify. Assigned geofences: {", ".join(assigned_geofence_names)}',
                'reason': 'out_of_assigned_geofence',
                'assigned_geofences': assigned_geofence_names
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create verification request
        with transaction.atomic():
            verification = VerificationRequest.objects.create(
                rider=rider,
                campaign=campaign,
                geofence=assigned_geofence,
                verification_type='random',
                location=rider_location,
                accuracy=float(validated_data['accuracy']),
                timestamp=timezone.now(),
                status='pending'
            )
            
            logger.info(f"Created random verification request {verification.id} for rider {rider.rider_id}")
            
            # Use the mobile-compatible serializer for consistent response
            serializer = MobileVerificationRequestSerializer(verification)
            
            return Response({
                'success': True,
                'verification': serializer.data
            }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error creating random verification: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response({
            'success': False,
            'message': 'Failed to create verification request'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_pending_verifications(request):
    """
    Check if rider has any pending verification requests
    
    GET /api/v1/verifications/pending/
    
    Returns the most recent pending verification if any
    """
    logger.info(f"=== CHECK PENDING VERIFICATIONS ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    
    try:
        rider = request.user.rider_profile
        
        # Get pending verifications for this rider
        pending_verifications = VerificationRequest.objects.filter(
            rider=rider,
            status='pending',
            # Only check verifications from last 30 minutes (expired after that)
            created_at__gte=timezone.now() - timedelta(minutes=30)
        ).order_by('-created_at')
        
        if not pending_verifications.exists():
            return Response({
                'success': True,
                'has_pending': False,
                'message': 'No pending verifications'
            })
        
        # Get the most recent pending verification
        verification = pending_verifications.first()
        
        # Check if it's still within the response window
        response_deadline = verification.created_at + timedelta(minutes=10)  # 10 minute window
        time_remaining = int((response_deadline - timezone.now()).total_seconds())
        
        if time_remaining <= 0:
            # Mark as failed due to timeout
            verification.status = 'failed'
            verification.ai_analysis = {
                'failure_reason': 'Response timeout',
                'processed_at': timezone.now().isoformat()
            }
            verification.save()
            
            return Response({
                'success': True,
                'has_pending': False,
                'message': 'Previous verification expired'
            })
        
        # Use mobile-compatible serializer for consistency
        serializer = MobileVerificationRequestSerializer(verification)
        
        return Response({
            'success': True,
            'has_pending': True,
            'verification': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Error checking pending verifications: {str(e)}")
        return Response({
            'success': False,
            'message': 'Failed to check pending verifications'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_verification(request):
    """
    Submit verification response (image + location)
    
    POST /api/v1/verifications/submit/
    
    Expected data (multipart/form-data):
    - verification_id: UUID
    - latitude: float
    - longitude: float
    - accuracy: float
    - image: file
    - timestamp: ISO string
    """
    logger.info(f"=== SUBMIT VERIFICATION ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Data keys: {list(request.data.keys())}")
    
    try:
        rider = request.user.rider_profile
        
        # Validate request data
        serializer = SubmitVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Invalid verification submission: {serializer.errors}")
            return Response({
                'success': False,
                'message': 'Invalid submission data',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        verification_id = serializer.validated_data['verification_id']
        
        # Get the verification request
        try:
            verification = VerificationRequest.objects.get(
                id=verification_id,
                rider=rider,
                status='pending'
            )
        except VerificationRequest.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Verification request not found or already completed'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if still within response window
        response_deadline = verification.created_at + timedelta(minutes=10)
        if timezone.now() > response_deadline:
            verification.status = 'failed'
            verification.ai_analysis = {
                'failure_reason': 'Response timeout',
                'processed_at': timezone.now().isoformat()
            }
            verification.save()
            
            return Response({
                'success': False,
                'message': 'Verification window expired'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check cooldown
        can_verify, cooldown_remaining = CooldownManager.check_cooldown(rider, verification.verification_type)
        if not can_verify:
            return Response({
                'success': False,
                'message': f'Please wait {int(cooldown_remaining)} seconds before trying again'
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
        
        # Update verification with submission data
        with transaction.atomic():
            verification.image = serializer.validated_data['image']
            verification.location = Point(
                float(serializer.validated_data['longitude']),
                float(serializer.validated_data['latitude'])
            )
            verification.accuracy = serializer.validated_data['accuracy']
            verification.timestamp = serializer.validated_data['timestamp']
            verification.status = 'processing'
            verification.save()
            
            # Process verification
            if verification.verification_type == 'random':
                verification_passed = VerificationProcessor.process_random_verification(verification)
            else:
                verification_passed = VerificationProcessor.process_join_verification(verification)
            
            # Set cooldown regardless of result
            CooldownManager.set_cooldown(rider, verification.verification_type)
            
            # Reload verification to get updated data
            verification.refresh_from_db()
            
            # Use mobile-compatible serializer for consistent response
            serializer = MobileVerificationRequestSerializer(verification)
            
            # Return result
            if verification_passed:
                logger.info(f"Verification {verification.id} passed for rider {rider.rider_id}")
                return Response({
                    'success': True,
                    'message': 'Verification completed successfully',
                    'verification': serializer.data
                })
            else:
                logger.warning(f"Verification {verification.id} failed for rider {rider.rider_id}")
                return Response({
                    'success': False,
                    'message': 'Verification failed: Image validation failed',
                    'verification': serializer.data
                }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Error submitting verification: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response({
            'success': False,
            'message': 'Failed to submit verification'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def verification_history(request):
    """
    Get rider's recent verification history
    
    GET /api/v1/verifications/history/
    """
    logger.info(f"=== VERIFICATION HISTORY ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    
    try:
        rider = request.user.rider_profile
        
        # Get recent verifications (last 7 days)
        recent_verifications = VerificationRequest.objects.filter(
            rider=rider,
            created_at__gte=timezone.now() - timedelta(days=7)
        ).order_by('-created_at')[:20]  # Limit to 20 most recent
        
        # Use mobile-compatible serializer for consistency
        serializer = MobileVerificationRequestSerializer(recent_verifications, many=True)
        
        return Response({
            'success': True,
            'verifications': serializer.data,
            'total_count': recent_verifications.count()
        })
        
    except Exception as e:
        logger.error(f"Error fetching verification history: {str(e)}")
        return Response({
            'success': False,
            'message': 'Failed to fetch verification history'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def verification_stats(request):
    """
    Get rider's verification statistics
    
    GET /api/v1/verifications/stats/
    """
    logger.info(f"=== VERIFICATION STATS ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    
    try:
        rider = request.user.rider_profile
        
        # Calculate stats
        all_verifications = VerificationRequest.objects.filter(rider=rider)
        
        total_verifications = all_verifications.count()
        passed_verifications = all_verifications.filter(status='passed').count()
        failed_verifications = all_verifications.filter(status='failed').count()
        
        success_rate = (passed_verifications / total_verifications * 100) if total_verifications > 0 else 0
        
        # Today's verifications
        today = timezone.now().date()
        verifications_today = all_verifications.filter(created_at__date=today).count()
        
        # This week's verifications
        week_start = timezone.now() - timedelta(days=7)
        verifications_this_week = all_verifications.filter(created_at__gte=week_start).count()
        
        # Last verification
        last_verification = all_verifications.order_by('-created_at').first()
        last_verification_date = last_verification.created_at if last_verification else None
        
        # Current streak (consecutive passed verifications)
        current_streak = 0
        recent_verifications = all_verifications.order_by('-created_at')[:10]
        for verification in recent_verifications:
            if verification.status == 'passed':
                current_streak += 1
            else:
                break
        
        # Average response time (in seconds)
        completed_verifications = all_verifications.filter(
            status__in=['passed', 'failed'],
            timestamp__isnull=False
        )
        
        avg_response_time = 0
        if completed_verifications.exists():
            total_response_time = 0
            count = 0
            for verification in completed_verifications:
                if verification.timestamp and verification.created_at:
                    response_time = (verification.timestamp - verification.created_at).total_seconds()
                    total_response_time += response_time
                    count += 1
            
            if count > 0:
                avg_response_time = total_response_time / count
        
        stats_data = {
            'total_verifications': total_verifications,
            'passed_verifications': passed_verifications,
            'failed_verifications': failed_verifications,
            'success_rate': round(success_rate, 2),
            'average_response_time': round(avg_response_time, 2),
            'last_verification': last_verification_date,
            'verifications_today': verifications_today,
            'verifications_this_week': verifications_this_week,
            'current_streak': current_streak
        }
        
        serializer = VerificationStatsSerializer(stats_data)
        
        return Response({
            'success': True,
            'stats': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Error fetching verification stats: {str(e)}")
        return Response({
            'success': False,
            'message': 'Failed to fetch verification stats'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)