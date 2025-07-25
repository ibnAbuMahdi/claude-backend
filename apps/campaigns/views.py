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
    Join an available campaign
    """
    logger.info(f"=== JOIN CAMPAIGN REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Data: {request.data}")
    
    try:
        # Validate request data
        serializer = CampaignJoinSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            logger.warning(f"Invalid join campaign request: {serializer.errors}")
            return Response({
                'success': False,
                'message': 'Invalid request',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        campaign_id = serializer.validated_data['campaign_id']
        rider = request.user.rider_profile
        
        # Get the campaign
        campaign = Campaign.objects.get(id=campaign_id)
        
        # Use the new geofence-aware assignment logic
        with transaction.atomic():
            # Set the assigned_by context for the campaign method
            campaign._assigned_by = request.user
            
            # Try to assign rider to the best available geofence
            geofence_assignment = campaign.assign_rider_to_best_geofence(rider)
            
            if geofence_assignment:
                # Get the campaign assignment that was created
                campaign_assignment = geofence_assignment.campaign_rider_assignment
                
                # Update rider availability if needed
                if hasattr(rider, 'current_campaign_count') and hasattr(rider, 'max_concurrent_campaigns'):
                    if rider.current_campaign_count >= rider.max_concurrent_campaigns:
                        rider.is_available = False
                        rider.save()
                
                logger.info(f"Rider {rider.rider_id} joined campaign {campaign.name} in geofence {geofence_assignment.campaign_geofence.name}")
                
                # Return assignment details including geofence info
                assignment_serializer = CampaignRiderAssignmentSerializer(campaign_assignment)
                geofence_serializer = CampaignGeofenceAssignmentSerializer(geofence_assignment)
                
                return Response({
                    'success': True,
                    'message': f'Successfully joined {campaign.name} in {geofence_assignment.campaign_geofence.name}',
                    'assignment': assignment_serializer.data,
                    'geofence_assignment': geofence_serializer.data,
                    'assigned_geofence': {
                        'id': str(geofence_assignment.campaign_geofence.id),
                        'name': geofence_assignment.campaign_geofence.name,
                        'rate_type': geofence_assignment.campaign_geofence.rate_type,
                        'rate_per_km': float(geofence_assignment.campaign_geofence.rate_per_km),
                        'rate_per_hour': float(geofence_assignment.campaign_geofence.rate_per_hour),
                        'fixed_daily_rate': float(geofence_assignment.campaign_geofence.fixed_daily_rate),
                    }
                })
            else:
                # Fallback to legacy assignment if no geofences available
                logger.warning(f"No available geofences for campaign {campaign.name}, using legacy assignment")
                
                assignment = CampaignRiderAssignment.objects.create(
                    campaign=campaign,
                    rider=rider,
                    status='assigned',
                    assigned_by=request.user
                )
                
                # Update rider availability if needed
                if hasattr(rider, 'current_campaign_count') and hasattr(rider, 'max_concurrent_campaigns'):
                    if rider.current_campaign_count >= rider.max_concurrent_campaigns:
                        rider.is_available = False
                        rider.save()
                
                logger.info(f"Rider {rider.rider_id} joined campaign {campaign.name} (legacy mode)")
                
                assignment_serializer = CampaignRiderAssignmentSerializer(assignment)
                
                return Response({
                    'success': True,
                    'message': f'Successfully joined {campaign.name}',
                    'assignment': assignment_serializer.data
                })
        
    except Campaign.DoesNotExist:
        logger.error(f"Campaign not found: {request.data.get('campaign_id')}")
        return Response({
            'success': False,
            'message': 'Campaign not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"=== JOIN CAMPAIGN ERROR ===")
        logger.error(f"User: {request.user.id} ({request.user.phone_number})")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response({
            'success': False,
            'message': 'Failed to join campaign'
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
def join_campaign_by_id(request, campaign_id):
    """
    Join campaign by ID (mobile app format: /campaigns/{id}/join/)
    """
    logger.info(f"=== JOIN CAMPAIGN BY ID REQUEST ===" )
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Campaign ID: {campaign_id}")
    
    # Create request data with campaign_id
    request.data['campaign_id'] = str(campaign_id)
    
    # Delegate to existing join_campaign function
    return join_campaign(request)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def leave_campaign_by_id(request, campaign_id):
    """
    Leave campaign by ID (mobile app format: /campaigns/{id}/leave/)
    """
    logger.info(f"=== LEAVE CAMPAIGN BY ID REQUEST ===" )
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Campaign ID: {campaign_id}")
    
    # Create request data with campaign_id
    request.data['campaign_id'] = str(campaign_id)
    
    # Delegate to existing leave_campaign function
    return leave_campaign(request)