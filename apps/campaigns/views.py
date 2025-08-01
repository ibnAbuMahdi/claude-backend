# apps/campaigns/views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.utils import timezone
from django.db import transaction
import logging

from .models import Campaign, CampaignRiderAssignment, CampaignGeofence, CampaignGeofenceAssignment
from .serializers import (
    CampaignSerializer, 
    CampaignJoinSerializer, 
    CampaignJoinWithVerificationSerializer,
    MyCampaignsSerializer,
    CampaignRiderAssignmentSerializer,
    CampaignGeofenceSerializer,
    CampaignGeofenceAssignmentSerializer
)
from apps.riders.models import Rider

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([AllowAny])  # Allow anonymous access
def available_campaigns(request):
    """
    Get available campaigns (public endpoint for browsing)
    Authentication is optional - if provided, will filter out campaigns rider already joined
    """
    logger.info(f"=== AVAILABLE CAMPAIGNS REQUEST ===")
    if request.user.is_authenticated:
        logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    else:
        logger.info("Anonymous user browsing campaigns")
    logger.info(f"Query params: {dict(request.GET)}")
    
    try:
        now = timezone.now()
        
        # Get active campaigns that are accepting riders
        campaigns = Campaign.objects.filter(
            status='active',
            start_date__lte=now,
            end_date__gte=now
        ).select_related(
            'client', 'agency'
        ).prefetch_related(
            'assigned_riders'
        )
        
        # Filter campaigns that have available spots
        available_campaigns = []
        rider = None
        
        # Get rider if user is authenticated
        if request.user.is_authenticated and hasattr(request.user, 'rider_profile'):
            rider = request.user.rider_profile
            logger.info(f"Authenticated rider: {rider.rider_id}")
        
        for campaign in campaigns:
            # Check if campaign has available geofence slots
            total_available_slots = campaign.get_total_available_slots()
            
            # Check if campaign has available spots (use geofence-aware method or fallback)
            if total_available_slots > 0:
                # If rider is authenticated, check if they haven't already joined
                if rider:
                    already_joined = campaign.assigned_riders.filter(
                        id=rider.id,
                        campaignriderassignment__status__in=['assigned', 'accepted', 'active']
                    ).exists()
                    
                    if not already_joined:
                        available_campaigns.append(campaign)
                else:
                    # For anonymous users, show all available campaigns
                    available_campaigns.append(campaign)
            else:
                # Fallback to legacy logic if no geofences defined
                current_riders = campaign.assigned_riders.filter(
                    campaignriderassignment__status__in=['assigned', 'accepted', 'active']
                ).count()
                
                if current_riders < campaign.required_riders:
                    if rider:
                        already_joined = campaign.assigned_riders.filter(
                            id=rider.id,
                            campaignriderassignment__status__in=['assigned', 'accepted', 'active']
                        ).exists()
                        
                        if not already_joined:
                            available_campaigns.append(campaign)
                    else:
                        available_campaigns.append(campaign)
        
        # Serialize the campaigns
        serializer = CampaignSerializer(
            available_campaigns, 
            many=True,
            context={'request': request}
        )
        
        logger.info(f"Found {len(available_campaigns)} available campaigns")
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"=== AVAILABLE CAMPAIGNS ERROR ===")
        if request.user.is_authenticated:
            logger.error(f"User: {request.user.id} ({request.user.phone_number})")
        else:
            logger.error("Anonymous user")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response({
            'success': False,
            'message': 'Failed to fetch campaigns',
            'data': []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def join_campaign(request):
    """
    Join a specific campaign geofence (location validation required)
    """
    logger.info(f"=== JOIN GEOFENCE REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Data: {request.data}")
    
    try:
        # Validate request data (now requires geofence_id and location)
        serializer = CampaignJoinSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            logger.warning(f"Invalid join geofence request: {serializer.errors}")
            return Response({
                'success': False,
                'message': 'Invalid request',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        campaign_id = serializer.validated_data['campaign_id']
        geofence_id = serializer.validated_data['geofence_id']
        rider_latitude = serializer.validated_data['latitude']
        rider_longitude = serializer.validated_data['longitude']
        rider = request.user.rider_profile
        
        # Get the campaign and geofence
        campaign = Campaign.objects.get(id=campaign_id)
        geofence = CampaignGeofence.objects.get(id=geofence_id)
        
        logger.info(f"Rider {rider.rider_id} attempting to join {geofence.name} in {campaign.name}")
        logger.info(f"Rider location: {rider_latitude}, {rider_longitude}")
        
        # Create geofence assignment with location validation already done by serializer
        with transaction.atomic():
            # Create campaign assignment first
            campaign_assignment = CampaignRiderAssignment.objects.create(
                campaign=campaign,
                rider=rider,
                status='assigned',
                assigned_by=request.user
            )
            
            # Create geofence assignment
            geofence_assignment = CampaignGeofenceAssignment.objects.create(
                campaign_geofence=geofence,
                rider=rider,
                campaign_rider_assignment=campaign_assignment,
                status='assigned',
                assigned_at=timezone.now()
            )
            
            # Update geofence rider count
            geofence.current_riders += 1
            geofence.save(update_fields=['current_riders'])
            
            # Update rider availability if needed
            if hasattr(rider, 'current_campaign_count') and hasattr(rider, 'max_concurrent_campaigns'):
                if rider.current_campaign_count >= rider.max_concurrent_campaigns:
                    rider.is_available = False
                    rider.save()
            
            logger.info(f"Successfully assigned rider {rider.rider_id} to geofence {geofence.name}")
            
            # Return assignment details
            assignment_serializer = CampaignRiderAssignmentSerializer(campaign_assignment)
            geofence_serializer = CampaignGeofenceAssignmentSerializer(geofence_assignment)
            
            return Response({
                'success': True,
                'message': f'Successfully joined {geofence.name} in {campaign.name}',
                'assignment': assignment_serializer.data,
                'geofence_assignment': geofence_serializer.data,
                'assigned_geofence': {
                    'id': str(geofence.id),
                    'name': geofence.name,
                    'rate_type': geofence.rate_type,
                    'rate_per_km': float(geofence.rate_per_km),
                    'rate_per_hour': float(geofence.rate_per_hour),
                    'fixed_daily_rate': float(geofence.fixed_daily_rate),
                    'center_latitude': float(geofence.center_latitude),
                    'center_longitude': float(geofence.center_longitude),
                    'radius_meters': geofence.radius_meters,
                }
            })
        
    except Campaign.DoesNotExist:
        logger.error(f"Campaign not found: {request.data.get('campaign_id')}")
        return Response({
            'success': False,
            'message': 'Campaign not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except CampaignGeofence.DoesNotExist:
        logger.error(f"Geofence not found: {request.data.get('geofence_id')}")
        return Response({
            'success': False,
            'message': 'Geofence not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"=== JOIN GEOFENCE ERROR ===")
        logger.error(f"User: {request.user.id} ({request.user.phone_number})")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response({
            'success': False,
            'message': 'Failed to join geofence'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_campaigns(request):
    """
    Get rider's active campaigns
    """
    logger.info(f"=== MY CAMPAIGNS REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    
    try:
        # Check if user has rider profile
        if not hasattr(request.user, 'rider_profile'):
            return Response({
                'success': False,
                'message': 'Rider profile required',
                'data': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        rider = request.user.rider_profile
        
        # Get rider's active campaigns
        assignments = CampaignRiderAssignment.objects.filter(
            rider=rider,
            status__in=['assigned', 'accepted', 'active']
        ).select_related(
            'campaign__client', 'campaign__agency'
        )
        
        campaigns = [assignment.campaign for assignment in assignments]
        
        serializer = MyCampaignsSerializer(
            campaigns, 
            many=True,
            context={'request': request}
        )
        
        logger.info(f"Returning {len(campaigns)} active campaigns for rider")
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"=== MY CAMPAIGNS ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response({
            'success': False,
            'message': 'Failed to fetch campaigns',
            'data': []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def leave_campaign(request):
    """
    Leave a campaign
    """
    logger.info(f"=== LEAVE CAMPAIGN REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Data: {request.data}")
    
    try:
        campaign_id = request.data.get('campaign_id')
        if not campaign_id:
            return Response({
                'success': False,
                'message': 'Campaign ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user has rider profile
        if not hasattr(request.user, 'rider_profile'):
            return Response({
                'success': False,
                'message': 'Rider profile required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        rider = request.user.rider_profile
        
        # Find the assignment
        try:
            assignment = CampaignRiderAssignment.objects.get(
                campaign_id=campaign_id,
                rider=rider,
                status__in=['assigned', 'accepted', 'active']
            )
        except CampaignRiderAssignment.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Campaign assignment not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        campaign_name = assignment.campaign.name
        
        # Update assignment status
        with transaction.atomic():
            assignment.status = 'cancelled'
            assignment.completed_at = timezone.now()
            assignment.save()
            
            # Update rider availability
            rider.is_available = True
            rider.save()
        
        logger.info(f"Rider {rider.rider_id} left campaign {campaign_name}")
        
        return Response({
            'success': True,
            'message': f'Successfully left {campaign_name}'
        })
        
    except Exception as e:
        logger.error(f"=== LEAVE CAMPAIGN ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response({
            'success': False,
            'message': 'Failed to leave campaign'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def geofence_details(request, geofence_id):
    """
    Get detailed information about a specific geofence
    """
    logger.info(f"=== GEOFENCE DETAILS REQUEST ===")
    if request.user.is_authenticated:
        logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    else:
        logger.info("Anonymous user")
    logger.info(f"Geofence ID: {geofence_id}")
    
    try:
        # Get the geofence with related campaign data
        geofence = CampaignGeofence.objects.select_related(
            'campaign__client', 'campaign__agency'
        ).get(id=geofence_id)
        
        serializer = CampaignGeofenceSerializer(
            geofence,
            context={'request': request}
        )
        
        return Response(serializer.data)
        
    except CampaignGeofence.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Geofence not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"=== GEOFENCE DETAILS ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response({
            'success': False,
            'message': 'Failed to fetch geofence details'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def campaign_details(request, campaign_id):
    """
    Get detailed information about a specific campaign
    """
    logger.info(f"=== CAMPAIGN DETAILS REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Campaign ID: {campaign_id}")
    
    try:
        # Get the campaign
        campaign = Campaign.objects.select_related(
            'client', 'agency'
        ).prefetch_related(
            'assigned_riders'
        ).get(id=campaign_id)
        
        serializer = CampaignSerializer(
            campaign,
            context={'request': request}
        )
        
        return Response(serializer.data)
        
    except Campaign.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Campaign not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"=== CAMPAIGN DETAILS ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response({
            'success': False,
            'message': 'Failed to fetch campaign details'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def join_geofence(request):
    """
    Join a specific geofence with location validation
    Expected data: {geofence_id, latitude, longitude}
    """
    logger.info(f"=== JOIN GEOFENCE REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Data: {request.data}")
    
    try:
        # Get geofence first to get campaign_id
        geofence_id = request.data.get('geofence_id')
        if not geofence_id:
            return Response({
                'success': False,
                'message': 'geofence_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            geofence = CampaignGeofence.objects.select_related('campaign').get(id=geofence_id)
        except CampaignGeofence.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Geofence not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Create request data with campaign_id added
        request_data = request.data.copy()
        request_data['campaign_id'] = str(geofence.campaign.id)
        
        # Validate request data using the serializer
        serializer = CampaignJoinSerializer(
            data=request_data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            logger.warning(f"Invalid join geofence request: {serializer.errors}")
            return Response({
                'success': False,
                'message': 'Invalid request',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        campaign_id = serializer.validated_data['campaign_id']
        rider_latitude = serializer.validated_data['latitude']
        rider_longitude = serializer.validated_data['longitude']
        rider = request.user.rider_profile
        
        # Get the campaign
        campaign = Campaign.objects.get(id=campaign_id)
        
        logger.info(f"Rider {rider.rider_id} attempting to join {geofence.name} in {campaign.name}")
        logger.info(f"Rider location: {rider_latitude}, {rider_longitude}")
        
        # Create geofence assignment with location validation already done by serializer
        with transaction.atomic():
            # Create campaign assignment first
            campaign_assignment = CampaignRiderAssignment.objects.create(
                campaign=campaign,
                rider=rider,
                status='assigned',
                assigned_by=request.user
            )
            
            # Create geofence assignment
            geofence_assignment = CampaignGeofenceAssignment.objects.create(
                campaign_geofence=geofence,
                rider=rider,
                campaign_rider_assignment=campaign_assignment,
                status='assigned',
                assigned_at=timezone.now()
            )
            
            # Update geofence rider count
            geofence.current_riders += 1
            geofence.save(update_fields=['current_riders'])
            
            # Update rider availability if needed
            if hasattr(rider, 'current_campaign_count') and hasattr(rider, 'max_concurrent_campaigns'):
                if rider.current_campaign_count >= rider.max_concurrent_campaigns:
                    rider.is_available = False
                    rider.save()
            
            logger.info(f"Successfully assigned rider {rider.rider_id} to geofence {geofence.name}")
            
            # Return assignment details
            assignment_serializer = CampaignRiderAssignmentSerializer(campaign_assignment)
            geofence_serializer = CampaignGeofenceAssignmentSerializer(geofence_assignment)
            
            return Response({
                'success': True,
                'message': f'Successfully joined {geofence.name} in {campaign.name}',
                'assignment': assignment_serializer.data,
                'geofence_assignment': geofence_serializer.data,
                'assigned_geofence': {
                    'id': str(geofence.id),
                    'name': geofence.name,
                    'rate_type': geofence.rate_type,
                    'rate_per_km': float(geofence.rate_per_km),
                    'rate_per_hour': float(geofence.rate_per_hour),
                    'fixed_daily_rate': float(geofence.fixed_daily_rate),
                    'center_latitude': float(geofence.center_latitude),
                    'center_longitude': float(geofence.center_longitude),
                    'radius_meters': geofence.radius_meters,
                }
            })
        
    except Campaign.DoesNotExist:
        logger.error(f"Campaign not found: {geofence.campaign.id}")
        return Response({
            'success': False,
            'message': 'Campaign not found'
        }, status=status.HTTP_404_NOT_FOUND)
        
    except Exception as e:
        logger.error(f"=== JOIN GEOFENCE ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response({
            'success': False,
            'message': 'Failed to join geofence'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def join_campaign_by_id(request, campaign_id):
    """
    DEPRECATED: Use join_geofence endpoint instead
    This endpoint now requires geofence_id and location data
    """
    logger.warning(f"=== DEPRECATED JOIN CAMPAIGN BY ID REQUEST ===" )
    logger.warning(f"User: {request.user.id} ({request.user.phone_number})")
    logger.warning(f"Campaign ID: {campaign_id}")
    
    # Check if geofence_id is provided (new requirement)
    if 'geofence_id' not in request.data:
        return Response({
            'success': False,
            'message': 'This endpoint now requires geofence_id and location data. Please use the /geofences/join/ endpoint or provide geofence_id, latitude, and longitude.',
            'upgrade_required': True
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Create request data with campaign_id
    request.data['campaign_id'] = str(campaign_id)
    
    # Delegate to existing join_campaign function
    return join_campaign(request)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def leave_geofence(request):
    """
    Leave a specific geofence
    Expected data: {geofence_id}
    """
    logger.info(f"=== LEAVE GEOFENCE REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Data: {request.data}")
    
    try:
        geofence_id = request.data.get('geofence_id')
        if not geofence_id:
            return Response({
                'success': False,
                'message': 'geofence_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user has rider profile
        if not hasattr(request.user, 'rider_profile'):
            return Response({
                'success': False,
                'message': 'Rider profile required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        rider = request.user.rider_profile
        
        # Find the geofence assignment
        try:
            geofence_assignment = CampaignGeofenceAssignment.objects.select_related(
                'campaign_geofence', 'campaign_rider_assignment'
            ).get(
                campaign_geofence_id=geofence_id,
                rider=rider,
                status__in=['assigned', 'active']
            )
        except CampaignGeofenceAssignment.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Geofence assignment not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        geofence_name = geofence_assignment.campaign_geofence.name
        campaign_name = geofence_assignment.campaign_geofence.campaign.name
        
        # Update assignments
        with transaction.atomic():
            # Cancel geofence assignment
            geofence_assignment.status = 'cancelled'
            geofence_assignment.completed_at = timezone.now()
            geofence_assignment.save()
            
            # Cancel campaign assignment if no other active geofences
            campaign_assignment = geofence_assignment.campaign_rider_assignment
            other_active_geofences = CampaignGeofenceAssignment.objects.filter(
                campaign_rider_assignment=campaign_assignment,
                status__in=['assigned', 'active']
            ).exclude(id=geofence_assignment.id).exists()
            
            if not other_active_geofences:
                campaign_assignment.status = 'cancelled'
                campaign_assignment.completed_at = timezone.now()
                campaign_assignment.save()
            
            # Update geofence rider count
            geofence = geofence_assignment.campaign_geofence
            geofence.current_riders = max(0, geofence.current_riders - 1)
            geofence.save(update_fields=['current_riders'])
            
            # Update rider availability
            rider.is_available = True
            rider.save()
        
        logger.info(f"Rider {rider.rider_id} left geofence {geofence_name} in campaign {campaign_name}")
        
        return Response({
            'success': True,
            'message': f'Successfully left {geofence_name} in {campaign_name}'
        })
        
    except Exception as e:
        logger.error(f"=== LEAVE GEOFENCE ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response({
            'success': False,
            'message': 'Failed to leave geofence'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def leave_campaign_by_id(request, campaign_id):
    """
    DEPRECATED: Use leave_geofence endpoint instead
    Leave campaign by ID (mobile app format: /campaigns/{id}/leave/)
    """
    logger.warning(f"=== DEPRECATED LEAVE CAMPAIGN BY ID REQUEST ===" )
    logger.warning(f"User: {request.user.id} ({request.user.phone_number})")
    logger.warning(f"Campaign ID: {campaign_id}")
    
    # Create request data with campaign_id
    request.data['campaign_id'] = str(campaign_id)
    
    # Delegate to existing leave_campaign function
    return leave_campaign(request)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def join_geofence_with_verification(request):
    """
    Join geofence with verification requirement
    Follows same pattern as existing join_geofence but adds verification step
    
    Expected data (multipart/form-data):
    - geofence_id: UUID
    - latitude: float
    - longitude: float
    - accuracy: float
    - image: file
    - timestamp: ISO string
    """
    from apps.verification.models import VerificationRequest
    from apps.verification.services import VerificationProcessor, CooldownManager, GeofenceJoinService
    from django.contrib.gis.geos import Point
    
    logger.info(f"=== JOIN GEOFENCE WITH VERIFICATION REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Data keys: {list(request.data.keys())}")
    
    try:
        # Get geofence first (same as existing join_geofence)
        geofence_id = request.data.get('geofence_id')
        if not geofence_id:
            return Response({
                'success': False,
                'message': 'geofence_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            geofence = CampaignGeofence.objects.select_related('campaign').get(id=geofence_id)
        except CampaignGeofence.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Geofence not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Create request data with campaign_id (same pattern)
        request_data = request.data.copy()
        request_data['campaign_id'] = str(geofence.campaign.id)
        
        # Use enhanced serializer for validation
        serializer = CampaignJoinWithVerificationSerializer(
            data=request_data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            logger.warning(f"Invalid join with verification request: {serializer.errors}")
            return Response({
                'success': False,
                'message': 'Invalid request',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check for duplicate (handle offline resilience)
        if serializer.validated_data.get('_is_duplicate'):
            existing_assignment = serializer.validated_data['_existing_assignment']
            logger.info(f"Duplicate join attempt - returning existing assignment")
            
            # Return success with existing assignment data
            assignment_serializer = CampaignRiderAssignmentSerializer(
                existing_assignment.campaign_rider_assignment
            )
            geofence_serializer = CampaignGeofenceAssignmentSerializer(existing_assignment)
            
            return Response({
                'success': True,
                'message': f'Already joined {geofence.name}',
                'was_duplicate': True,
                'assignment': assignment_serializer.data,
                'geofence_assignment': geofence_serializer.data,
                'verification_id': 'existing'
            })
        
        # Process verification and join atomically
        with transaction.atomic():
            rider = request.user.rider_profile
            
            # 1. Create verification request
            verification = VerificationRequest.objects.create(
                rider=rider,
                campaign=geofence.campaign,
                geofence=geofence,  # New field
                verification_type='geofence_join',  # New field
                image=serializer.validated_data['image'],
                location=Point(
                    float(serializer.validated_data['longitude']),
                    float(serializer.validated_data['latitude'])
                ),
                accuracy=float(serializer.validated_data['accuracy']),
                timestamp=serializer.validated_data['timestamp'],
                image_metadata={
                    'geofence_join_attempt': True,
                    'geofence_id': str(geofence_id),
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                }
            )
            
            # 2. Process verification (basic image validation for now)
            verification_passed = VerificationProcessor.process_join_verification(verification)
            
            if not verification_passed:
                # Set cooldown and return failure
                CooldownManager.set_cooldown(rider, 'geofence_join')
                
                return Response({
                    'success': False,
                    'message': 'Verification failed: Invalid image or sticker not detected',
                    'verification_id': str(verification.id),
                    'verification_status': verification.status
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 3. Verification passed - proceed with join (reuse existing logic)
            campaign_assignment, geofence_assignment = GeofenceJoinService.create_join_with_verification(
                rider=rider,
                geofence=geofence,
                verification_request=verification,
                assigned_by=request.user
            )
            
            # 4. Update rider availability (same as existing)
            if hasattr(rider, 'current_campaign_count') and hasattr(rider, 'max_concurrent_campaigns'):
                if rider.current_campaign_count >= rider.max_concurrent_campaigns:
                    rider.is_available = False
                    rider.save()
            
            logger.info(f"Successfully assigned rider {rider.rider_id} to geofence {geofence.name} with verification")
            
            # Return response (same format as existing join_geofence)
            assignment_serializer = CampaignRiderAssignmentSerializer(campaign_assignment)
            geofence_serializer = CampaignGeofenceAssignmentSerializer(geofence_assignment)
            
            return Response({
                'success': True,
                'message': f'Successfully joined {geofence.name} with verification',
                'verification_id': str(verification.id),
                'assignment': assignment_serializer.data,
                'geofence_assignment': geofence_serializer.data,
                'assigned_geofence': {
                    'id': str(geofence.id),
                    'name': geofence.name,
                    'rate_type': geofence.rate_type,
                    'rate_per_km': float(geofence.rate_per_km),
                    'rate_per_hour': float(geofence.rate_per_hour),
                    'fixed_daily_rate': float(geofence.fixed_daily_rate),
                    'center_latitude': float(geofence.center_latitude),
                    'center_longitude': float(geofence.center_longitude),
                    'radius_meters': geofence.radius_meters,
                }
            }, status=status.HTTP_201_CREATED)
            
    except Exception as e:
        logger.error(f"=== JOIN GEOFENCE WITH VERIFICATION ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response({
            'success': False,
            'message': 'Failed to join geofence with verification'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_geofence_join_eligibility(request):
    """
    Check if rider can join a geofence without actually joining
    Query params: geofence_id, latitude, longitude
    """
    from apps.verification.services import GeofenceJoinService, CooldownManager
    
    logger.info(f"=== CHECK GEOFENCE JOIN ELIGIBILITY REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Query params: {dict(request.GET)}")
    
    try:
        # Get parameters
        geofence_id = request.data.get('geofence_id')
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        
        if not all([geofence_id, latitude, longitude]):
            return Response({
                'can_join': False,
                'reasons': ['geofence_id, latitude, and longitude are required'],
                'error': 'Missing required parameters'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            geofence = CampaignGeofence.objects.select_related('campaign').get(id=geofence_id)
        except CampaignGeofence.DoesNotExist:
            return Response({
                'can_join': False,
                'reasons': ['Geofence not found'],
                'error': 'Geofence not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user has rider profile
        if not hasattr(request.user, 'rider_profile'):
            return Response({
                'can_join': False,
                'reasons': ['Rider profile required'],
                'error': 'Rider profile required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        rider = request.user.rider_profile
        reasons = []
        
        # Check geofence eligibility
        is_eligible, error_message = GeofenceJoinService.validate_geofence_eligibility(
            rider, geofence, float(latitude), float(longitude)
        )
        
        if not is_eligible:
            reasons.append(error_message)
        
        # Check verification cooldown
        can_verify, cooldown_remaining = CooldownManager.check_cooldown(rider, 'geofence_join')
        if not can_verify:
            reasons.append(f'Please wait {int(cooldown_remaining)} seconds before trying again')
        
        response_data = {
            'can_join': is_eligible and can_verify,
            'reasons': reasons,
            'cooldown_remaining': int(cooldown_remaining) if not can_verify else 0,
            'geofence_info': {
                'id': str(geofence.id),
                'name': geofence.name,
                'campaign_name': geofence.campaign.name,
                'available_slots': geofence.available_slots,
                'is_active': geofence.is_active,
                'rate_type': geofence.rate_type,
                'rate_per_km': float(geofence.rate_per_km),
                'rate_per_hour': float(geofence.rate_per_hour),
                'fixed_daily_rate': float(geofence.fixed_daily_rate),
            }
        }
        
        logger.info(f"Eligibility check result: can_join={response_data['can_join']}")
        return Response(response_data)
        
    except Exception as e:
        logger.error(f"=== CHECK GEOFENCE JOIN ELIGIBILITY ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response({
            'can_join': False,
            'reasons': ['Internal server error'],
            'error': 'Failed to check eligibility'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_tracking_status(request):
    """
    Get tracking status for the authenticated rider based on geofence assignments
    Returns whether the rider should be tracking location and which geofences they're assigned to
    """
    logger.info(f"=== GET TRACKING STATUS REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    
    try:
        rider = request.user.rider_profile
        logger.info(f"Rider: {rider.rider_id}")
        
        # Get active geofence assignments
        active_assignments = CampaignGeofenceAssignment.objects.filter(
            rider=rider,
            status='active'
        ).select_related('campaign_geofence', 'campaign')
        
        should_track = active_assignments.exists()
        logger.info(f"Should track: {should_track} (found {active_assignments.count()} active assignments)")
        
        tracking_data = {
            'should_track': should_track,
            'active_assignments_count': active_assignments.count(),
            'active_assignments': []
        }
        
        for assignment in active_assignments:
            geofence = assignment.campaign_geofence
            campaign = assignment.campaign
            
            assignment_data = {
                'assignment_id': str(assignment.id),
                'geofence_id': str(geofence.id),
                'geofence_name': geofence.name,
                'campaign_id': str(campaign.id),
                'campaign_name': campaign.name,
                'center_latitude': float(geofence.center_latitude),
                'center_longitude': float(geofence.center_longitude),
                'radius_meters': geofence.radius_meters,
                'rate_type': geofence.rate_type,
                'rate_per_km': float(geofence.rate_per_km) if geofence.rate_per_km else None,
                'rate_per_hour': float(geofence.rate_per_hour) if geofence.rate_per_hour else None,
                'joined_at': assignment.joined_at.isoformat() if assignment.joined_at else None,
            }
            tracking_data['active_assignments'].append(assignment_data)
            logger.info(f"  - {geofence.name} in {campaign.name}")
        
        logger.info(f"Tracking status response: {tracking_data}")
        return Response(tracking_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"=== GET TRACKING STATUS ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response(
            {'error': f'Failed to get tracking status: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )