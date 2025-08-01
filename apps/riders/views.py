# apps/riders/views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
import logging

from .models import Rider
from .serializers import (
    RiderActivationSerializer, 
    RiderSerializer, 
    PlateNumberValidationSerializer
)

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rider_earnings(request):
    """
    Get rider earnings data
    TODO: Implement actual earnings logic
    """
    logger.info(f"=== RIDER EARNINGS REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Query params: {dict(request.GET)}")
    logger.info(f"Method: {request.method}")
    logger.info(f"Path: {request.path}")
    
    try:
        # Return earnings data in expected format with pagination
        response_data = {
            'results': [],  # Empty list of earnings
            'count': 0,
            'next': None,
            'previous': None
        }
        
        logger.info(f"Successfully returning earnings response: {response_data}")
        return Response(response_data)
    except Exception as e:
        logger.error(f"=== RIDER EARNINGS ERROR ===")
        logger.error(f"User: {request.user.id} ({request.user.phone_number})")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        error_response = {
            'results': [],
            'count': 0,
            'next': None,
            'previous': None
        }
        
        logger.error(f"Returning error response: {error_response}")
        return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_summary(request):
    """
    Get rider payment summary
    TODO: Implement actual payment summary logic
    """
    logger.info(f"=== PAYMENT SUMMARY REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Query params: {dict(request.GET)}")
    logger.info(f"Method: {request.method}")
    logger.info(f"Path: {request.path}")
    
    try:
        # Return payment summary in expected format
        response_data = {
            'total_earnings': 0.0,
            'pending_earnings': 0.0,
            'paid_earnings': 0.0,
            'this_week_earnings': 0.0,
            'this_month_earnings': 0.0,
            'total_hours': 0,
            'total_verifications': 0,
            'active_campaigns': 0,
            'last_payment': '2024-01-01T00:00:00Z',
            'preferred_payment_method': 'bank_transfer',
            'recent_earnings': []
        }
        
        logger.info(f"Successfully returning payment summary: {response_data}")
        return Response(response_data)
    except Exception as e:
        logger.error(f"=== PAYMENT SUMMARY ERROR ===")
        logger.error(f"User: {request.user.id} ({request.user.phone_number})")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        error_response = {
            'total_earnings': 0.0,
            'pending_earnings': 0.0,
            'paid_earnings': 0.0,
            'this_week_earnings': 0.0,
            'this_month_earnings': 0.0,
            'total_hours': 0,
            'total_verifications': 0,
            'active_campaigns': 0,
            'last_payment': '2024-01-01T00:00:00Z',
            'preferred_payment_method': 'bank_transfer',
            'recent_earnings': []
        }
        
        logger.error(f"Returning error response: {error_response}")
        return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def activate_rider(request):
    """
    Activate rider with plate number
    """
    logger.info(f"=== RIDER ACTIVATION REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Data: {request.data}")
    
    try:
        # Get rider instance
        try:
            rider = get_object_or_404(Rider, user=request.user)
        except Exception as e:
            logger.error(f"Rider not found for user {request.user.id}: {str(e)}")
            return Response(
                {'error': 'Rider profile not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Validate request data
        serializer = RiderActivationSerializer(data=request.data)
        if not serializer.is_valid():
            logger.error(f"Validation errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Activate rider
        with transaction.atomic():
            try:
                activated_rider = serializer.activate_rider(rider)
                response_serializer = RiderSerializer(activated_rider)
                
                logger.info(f"Rider {rider.rider_id} activated successfully")
                return Response({
                    'message': 'Rider activated successfully',
                    'rider': response_serializer.data
                }, status=status.HTTP_200_OK)
                
            except Exception as activation_error:
                logger.error(f"Activation failed: {str(activation_error)}")
                return Response(
                    {'error': str(activation_error)}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
                
    except Exception as e:
        logger.error(f"=== RIDER ACTIVATION ERROR ===")
        logger.error(f"User: {request.user.id}")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response(
            {'error': 'Internal server error'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_plate_number(request):
    """
    Validate plate number without activation
    """
    logger.info(f"=== PLATE VALIDATION REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Data: {request.data}")
    
    try:
        serializer = PlateNumberValidationSerializer(data=request.data)
        if serializer.is_valid():
            logger.info(f"Plate number validation successful")
            return Response({
                'message': 'Plate number is valid',
                'plate_number': serializer.validated_data['plate_number']
            }, status=status.HTTP_200_OK)
        else:
            logger.error(f"Plate validation errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"=== PLATE VALIDATION ERROR ===")
        logger.error(f"User: {request.user.id}")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response(
            {'error': 'Internal server error'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rider_profile(request):
    """
    Get rider profile information
    """
    logger.info(f"=== RIDER PROFILE REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    
    try:
        rider = get_object_or_404(Rider, user=request.user)
        serializer = RiderSerializer(rider)
        
        logger.info(f"Rider profile retrieved successfully")
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"=== RIDER PROFILE ERROR ===")
        logger.error(f"User: {request.user.id}")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response(
            {'error': 'Rider profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )