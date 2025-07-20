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
        # Return earnings data in expected format
        return Response({
            'earnings': [],
            'has_more': False
        })
    except Exception as e:
        logger.error(f"Rider earnings error: {str(e)}")
        return Response({
            'earnings': [],
            'has_more': False
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_summary(request):
    """
    Get rider payment summary
    TODO: Implement actual payment summary logic
    """
    try:
        # Return empty payment summary for now to prevent app crashes
        return Response({
            'success': True,
            'this_week_earnings': 0.0,
            'pending_earnings': 0.0,
            'paid_earnings': 0.0,
            'total_earnings': 0.0,
            'formatted_this_week_earnings': '₦0.00',
            'formatted_pending_earnings': '₦0.00',
            'formatted_paid_earnings': '₦0.00',
            'formatted_total_earnings': '₦0.00',
            'message': 'No payment data available yet'
        })
    except Exception as e:
        logger.error(f"Payment summary error: {str(e)}")
        return Response({
            'success': False,
            'this_week_earnings': 0.0,
            'pending_earnings': 0.0,
            'paid_earnings': 0.0,
            'total_earnings': 0.0,
            'formatted_this_week_earnings': '₦0.00',
            'formatted_pending_earnings': '₦0.00',
            'formatted_paid_earnings': '₦0.00',
            'formatted_total_earnings': '₦0.00',
            'message': 'Failed to load payment summary'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)