# apps/riders/views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
import logging

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rider_earnings(request):
    """
    Get rider earnings data
    TODO: Implement actual earnings logic
    """
    try:
        # Return empty earnings data for now to prevent app crashes
        # Return earnings data in expected format with pagination
        return Response({
            'results': [],  # Empty list of earnings
            'count': 0,
            'next': None,
            'previous': None
        })
    except Exception as e:
        logger.error(f"Rider earnings error: {str(e)}")
        return Response({
            'results': [],
            'count': 0,
            'next': None,
            'previous': None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_summary(request):
    """
    Get rider payment summary
    TODO: Implement actual payment summary logic
    """
    try:
        # Return payment summary in expected format
        return Response({
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
        })
    except Exception as e:
        logger.error(f"Payment summary error: {str(e)}")
        return Response({
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
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)